"""The run state machine, its in-memory registry, and the worker thread.

Only one run executes at a time — `outputs/` is a single shared workspace with
fixed filenames, so concurrent runs would overwrite each other's assets. That
constraint is what makes it safe for the worker to swap `config` module
attributes for per-run overrides.

State is intentionally in-memory. Restarting the server loses run history;
`generated_data/` is the durable record.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pipeline
from api.config_view import apply_overrides
from models import Script, save_script, with_estimated_timings
from utils.openai_support import TaskResult
from utils.paths import script_path, slugify

STATUS_PENDING = "pending"
STATUS_GENERATING_SCRIPT = "generating_script"
STATUS_GENERATING_PROMPTS = "generating_prompts"
STATUS_AWAITING_REVIEW = "awaiting_review"

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# The stage display order lives in the frontend (`STAGE_SEQUENCE` in
# `frontend/src/lib/types.ts`); the backend only reports the current status.

_MAX_LOG_LINES = 500


class RunConflictError(RuntimeError):
    """The requested transition does not match the run's current state."""


class RunNotFoundError(KeyError):
    """No run with that id exists in this process."""


class _Cancelled(Exception):
    """Internal signal that the run was cancelled between stages."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AssetStatus:
    """The outcome of one generated asset within the current stage."""

    label: str
    ok: bool
    error: str | None = None


@dataclass
class Run:
    """Everything the UI needs to render one run."""

    id: str
    topic: str
    target_seconds: int
    review_script: bool
    overrides: dict[str, Any]
    status: str = STATUS_PENDING
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    script: Script = field(default_factory=lambda: Script(topic="", title=""))
    assets: list[AssetStatus] = field(default_factory=list)
    asset_total: int = 0
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    video_path: Path | None = None
    archive_slug: str | None = None


@dataclass
class _Gate:
    """The two events the worker blocks on or checks between stages."""

    review: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)


class RunStore:
    """Registry of runs plus the worker that executes them, one at a time."""

    def __init__(self, *, client=None) -> None:
        self._client = client
        self._lock = threading.RLock()
        self._runs: dict[str, Run] = {}
        self._order: list[str] = []
        self._gates: dict[str, _Gate] = {}
        self._threads: dict[str, threading.Thread] = {}

    # --- reads -----------------------------------------------------------

    def get(self, run_id: str) -> Run:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise RunNotFoundError(run_id) from exc

    def list(self) -> list[Run]:
        """Newest first."""
        with self._lock:
            return [self._runs[run_id] for run_id in reversed(self._order)]

    def active(self) -> Run | None:
        with self._lock:
            for run in self._runs.values():
                if run.status not in TERMINAL_STATUSES:
                    return run
        return None

    # --- transitions -----------------------------------------------------

    def start(
        self,
        topic: str,
        target_seconds: int,
        *,
        review_script: bool,
        overrides: dict[str, Any],
    ) -> Run:
        """Register a run and execute it on a daemon thread."""
        with self._lock:
            active = self.active()
            if active is not None:
                raise RunConflictError(
                    f"run {active.id} is still {active.status}; "
                    f"only one run can be active at a time"
                )
            run = Run(
                id=uuid.uuid4().hex[:12],
                topic=topic,
                target_seconds=target_seconds,
                review_script=review_script,
                overrides=dict(overrides),
            )
            self._runs[run.id] = run
            self._order.append(run.id)
            self._gates[run.id] = _Gate()

            thread = threading.Thread(
                target=self._execute, args=(run,), name=f"run-{run.id}", daemon=True
            )
            self._threads[run.id] = thread

        thread.start()
        return run

    def approve_script(self, run_id: str, script: Script) -> Run:
        """Replace the run's script with the edited one and let it continue.

        `start`/`end` are output-only on the wire, but `parse_script` still
        accepts whatever a client sends (it is shared with the archive-load
        path, which must preserve measured timings read from disk). Re-derive
        them here from the — possibly edited — narration so a client-supplied
        timing never survives review, and an edited narration is reflected in
        its own timing rather than a stale estimate for the old text.
        """
        script = with_estimated_timings(script)
        with self._lock:
            run = self.get(run_id)
            if run.status != STATUS_AWAITING_REVIEW:
                raise RunConflictError(
                    f"run {run_id} is {run.status}, not {STATUS_AWAITING_REVIEW}"
                )
            run.script = script
            gate = self._gates[run_id]

        # Overwrite the saved script so the archive reflects the edits.
        save_script(run.script, script_path())
        gate.review.set()
        return run

    def cancel(self, run_id: str) -> Run:
        """Ask the run to stop at the next checkpoint."""
        with self._lock:
            run = self.get(run_id)
            if run.status in TERMINAL_STATUSES:
                raise RunConflictError(f"run {run_id} is already {run.status}")
            gate = self._gates[run_id]

        gate.cancel.set()
        # Wake a run that is parked on the review gate so it can see the flag.
        gate.review.set()
        return run

    # --- test helpers ----------------------------------------------------

    def wait_for_idle(self, timeout: float = 10.0) -> None:
        """Block until no run thread is alive. Used by tests."""
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError(f"{thread.name} did not finish in {timeout}s")

    def wait_for_status(self, run_id: str, status: str, timeout: float = 10.0) -> Run:
        """Block until the run reaches `status`. Used by tests."""
        idle = threading.Event()
        elapsed = 0.0
        step = 0.01
        while elapsed < timeout:
            run = self.get(run_id)
            if run.status == status:
                return run
            if run.status in TERMINAL_STATUSES:
                raise AssertionError(
                    f"run {run_id} reached {run.status} without hitting {status}: "
                    f"{run.error}"
                )
            idle.wait(step)
            elapsed += step
        raise TimeoutError(f"run {run_id} never reached {status}")

    # --- internals -------------------------------------------------------

    def _set_status(self, run: Run, status: str) -> None:
        with self._lock:
            run.status = status
            if status in TERMINAL_STATUSES:
                run.finished_at = _now()

    def _log(self, run: Run, message: str) -> None:
        with self._lock:
            run.logs.append(message)
            if len(run.logs) > _MAX_LOG_LINES:
                del run.logs[: len(run.logs) - _MAX_LOG_LINES]

    def _begin_asset_stage(self, run: Run, total: int) -> None:
        """Asset counts are scoped to the current stage, not the whole run."""
        with self._lock:
            run.assets = []
            run.asset_total = total

    def _record_asset(self, run: Run, result: TaskResult) -> None:
        status = AssetStatus(
            label=result.label,
            ok=result.ok,
            error=(
                None if result.ok else f"{type(result.error).__name__}: {result.error}"
            ),
        )
        with self._lock:
            run.assets.append(status)

    def _check_cancelled(self, gate: _Gate) -> None:
        if gate.cancel.is_set():
            raise _Cancelled()

    def _execute(self, run: Run) -> None:
        gate = self._gates[run.id]

        def log(message: str) -> None:
            self._log(run, message)

        try:
            with apply_overrides(run.overrides):
                self._check_cancelled(gate)
                self._set_status(run, STATUS_GENERATING_SCRIPT)
                script = pipeline.generate_script_stage(
                    run.topic, run.target_seconds, client=self._client, log=log
                )

                self._check_cancelled(gate)
                self._set_status(run, STATUS_GENERATING_PROMPTS)
                script = pipeline.generate_prompts_stage(
                    script, client=self._client, log=log
                )
                with self._lock:
                    run.script = script

                if run.review_script:
                    self._set_status(run, STATUS_AWAITING_REVIEW)
                    log("Waiting for you to review the script...")
                    gate.review.wait()
                    self._check_cancelled(gate)
                    with self._lock:
                        script = run.script
                    log(f"Continuing with {len(script.sections)} approved section(s).")

                self._check_cancelled(gate)
                self._set_status(run, "generating_media")
                self._begin_asset_stage(run, pipeline.media_job_total(script))
                pipeline.generate_media_stage(
                    script,
                    client=self._client,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "composing_frames")
                self._begin_asset_stage(run, pipeline.compose_job_total(script))
                pipeline.compose_stage(
                    script,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "rendering_video")
                self._begin_asset_stage(run, 0)
                video, durations = pipeline.render_video_stage(script, log=log)
                with self._lock:
                    run.video_path = video

                self._check_cancelled(gate)
                self._set_status(run, "archiving")
                pipeline.archive_stage(script, durations, log=log)
                with self._lock:
                    run.archive_slug = slugify(run.topic)

            self._set_status(run, "completed")
            log("Done.")
        except _Cancelled:
            log("Cancelled.")
            self._set_status(run, "cancelled")
        except BaseException as exc:  # noqa: BLE001 - surfaced on the run
            with self._lock:
                run.error = f"{type(exc).__name__}: {exc}"
            log(f"Failed: {run.error}")
            self._set_status(run, "failed")
