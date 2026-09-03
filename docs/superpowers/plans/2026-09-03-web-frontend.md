# Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a React + shadcn/ui web frontend on the existing Python video pipeline, backed by a FastAPI server in this repo, so a run can be started, watched stage-by-stage, paused for item editing, and browsed afterwards.

**Architecture:** `pipeline.py` splits into five independently callable stage functions; `run_pipeline` keeps working by composing them, so the CLI is unchanged. A FastAPI app in `api/` runs one pipeline at a time on a background thread, recording stage, per-asset results and logs into an in-memory `Run` object that the UI polls every 2 seconds. `outputs/` and `generated_data/` are mounted as static files so the browser can play the audio, images and video directly. The frontend is a Vite + React + TypeScript SPA in `frontend/` that proxies `/api` and `/media` to the backend in development.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, pytest (backend). Vite, React 19, TypeScript, React Router, Tailwind CSS v4, shadcn/ui, Vitest + React Testing Library (frontend).

**Spec:** No separate spec document. The requirements were settled in-conversation and are reproduced in full under "Product Decisions" below; treat that section as the spec.

---

## Product Decisions

These were chosen by the user. They are requirements, not suggestions.

1. **Backend:** FastAPI inside this repo, importing the pipeline directly. Not a subprocess wrapper.
2. **Progress:** job + polling. `POST /api/runs` returns a run id immediately; the UI polls `GET /api/runs/{id}`.
3. **Screens:** all four — new run + live progress, archive browser, config viewer with per-run overrides, and an item review/edit pause between the list stage and the media stage.
4. **Frontend:** Vite + React + TypeScript in `frontend/`, Tailwind v4, shadcn/ui. Styling stays deliberately plain — default shadcn components, no custom theme work. Visual design is explicitly out of scope for this plan.

## Global Constraints

- **One run at a time.** `outputs/` is a single shared workspace with fixed filenames (`item_01_prompt_01.png`, …). Two concurrent runs would overwrite each other. `POST /api/runs` returns **409** while a non-terminal run exists.
- **The API server must be started from the repository root.** Every path in `utils/paths.py` is relative to the current working directory by design (so tests can `chdir`). Run it as `uvicorn api.app:app --port 8000` from the repo root.
- **Run state is in-memory only.** Restarting the server loses run history. Archives in `generated_data/` are the durable record. Do not add a database.
- **Do not change CLI behaviour.** `python main.py --topic X --items 5` must print the same `[n/5]` banners and produce the same files after the refactor. `tests/test_pipeline.py` must keep passing untouched.
- **Do not upgrade `moviepy` (pinned `1.0.3`) or `decorator` (pinned `4.4.2`).** Upgrading either breaks video assembly.
- **Tests never make network calls.** Every OpenAI interaction goes through an injected fake client. The whole suite must pass with `OPENAI_API_KEY` unset.
- **Cancellation is cooperative.** The cancel flag is checked between stages and while waiting for review. An in-flight moviepy render or OpenAI batch is not interrupted. Say this in the UI; do not pretend otherwise.
- **Config override names are exactly the `config.py` constant names** (`IMAGE_QUALITY`, `VIDEO_PRESET`, …), uppercase, on the wire and in the UI.
- **Backend Python style matches the existing code:** module docstring on every file, type hints on public functions, docstrings that explain *why* rather than restate the signature.

## File Structure

**New — backend (`api/`, one responsibility per file):**

| File | Responsibility |
|---|---|
| `api/__init__.py` | Empty package marker. |
| `api/app.py` | `create_app()` factory: static mounts, CORS, router wiring, run-store construction. |
| `api/routes.py` | Every HTTP endpoint. Translates domain errors into status codes. No business logic. |
| `api/schemas.py` | Pydantic request/response models. The single source of the wire contract. |
| `api/runs.py` | `Run`, `RunStore`, the background worker and the run state machine. |
| `api/config_view.py` | Effective-config introspection, the override allowlist, validation, and the override context manager. |
| `api/archives.py` | Reads `generated_data/` into listing and detail payloads with media URLs. |

**Modified — backend:**

| File | Change |
|---|---|
| `pipeline.py` | Split into five stage functions; `run_pipeline` becomes their composition. |
| `utils/openai_support.py` | `run_all` gains an optional `on_done` callback for incremental progress. |
| `scripts/non_ai/create_titled_images_short/create_titled_images_short.py` | `create_titled_images_for_items_short` gains `on_done`. |
| `scripts/ai/generate_list/generate_list.py` | Pass `expected_prompts` explicitly — the current import-time default ignores overrides. |
| `models.py` | Reject an empty `image_prompts` list (currently passes validation and breaks the renderer). |
| `requirements.txt` | Add `fastapi`, `uvicorn[standard]`, `httpx`. |
| `README.md` | Document the web UI and how to run both processes. |

**New — frontend (`frontend/`):**

| File | Responsibility |
|---|---|
| `src/lib/types.ts` | TypeScript mirror of `api/schemas.py`. |
| `src/lib/api.ts` | Typed `fetch` wrapper, one function per endpoint, `ApiError`. |
| `src/hooks/useRun.ts` | Polls one run until it reaches a terminal status. |
| `src/components/StageProgress.tsx` | The five-stage indicator plus the current stage's asset counter. |
| `src/components/AssetList.tsx` | Per-asset ok/failed rows. |
| `src/components/ItemEditor.tsx` | Editable title / description / image prompts for one item. |
| `src/components/LogPanel.tsx` | Scrolling log output. |
| `src/pages/NewRunPage.tsx` | Topic, item count, review toggle, per-run overrides. |
| `src/pages/RunPage.tsx` | Live progress; swaps in the review editor at `awaiting_review`. |
| `src/pages/ArchivesPage.tsx` | Archive list. |
| `src/pages/ArchiveDetailPage.tsx` | One archive's items, images, audio and video. |
| `src/pages/ConfigPage.tsx` | Effective config table, editable fields marked. |
| `src/App.tsx` | Router and nav shell. |

---

### Task 1: Incremental progress from `run_all`

`run_all` currently returns only after every job finishes, so the UI could not show media generation advancing. Add an optional per-job callback while keeping the existing return contract (results in **submission** order) byte-for-byte identical.

**Files:**
- Modify: `utils/openai_support.py:74-89` (`run_all`)
- Modify: `scripts/non_ai/create_titled_images_short/create_titled_images_short.py:33-40`
- Test: `tests/test_openai_support.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `run_all(executor, jobs, *, on_done: Callable[[TaskResult], None] | None = None) -> list[TaskResult]` and `create_titled_images_for_items_short(items, *, on_done=None) -> list[TaskResult]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_openai_support.py`:

```python
def test_run_all_reports_each_result_as_it_finishes():
    from concurrent.futures import ThreadPoolExecutor

    from utils.openai_support import run_all

    seen = []
    jobs = [("a", lambda: 1), ("b", lambda: 2), ("c", lambda: 3)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = run_all(executor, jobs, on_done=seen.append)

    assert [r.label for r in results] == ["a", "b", "c"]
    assert sorted(r.label for r in seen) == ["a", "b", "c"]


def test_run_all_reports_failures_to_the_callback():
    from concurrent.futures import ThreadPoolExecutor

    from utils.openai_support import run_all

    def boom():
        raise ValueError("nope")

    seen = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        run_all(executor, [("bad", boom)], on_done=seen.append)

    assert len(seen) == 1
    assert not seen[0].ok
    assert isinstance(seen[0].error, ValueError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_openai_support.py -v`
Expected: FAIL with `TypeError: run_all() got an unexpected keyword argument 'on_done'`

- [ ] **Step 3: Rewrite `run_all`**

Replace the body of `run_all` in `utils/openai_support.py`. Add `as_completed` to the existing `concurrent.futures` import at the top of the file so it reads `from concurrent.futures import Executor, as_completed`, and add `Callable` to the `typing` import if it is not already there (it is).

```python
def run_all(
    executor: Executor,
    jobs: Sequence[Job],
    *,
    on_done: Callable[[TaskResult], None] | None = None,
) -> list[TaskResult]:
    """Run every job on `executor`, returning results in submission order.

    A failing job does not stop the others; its exception is captured on the
    corresponding `TaskResult`. Passing a shared executor lets several stages
    interleave their work under one global concurrency cap.

    `on_done` is invoked in *completion* order, which is what a progress
    display wants; the returned list stays in submission order, which is what
    every existing caller expects.
    """
    submitted = [(label, executor.submit(fn)) for label, fn in jobs]
    labels = {future: label for label, future in submitted}

    outcomes: dict[Any, TaskResult] = {}
    for future in as_completed(labels):
        label = labels[future]
        try:
            result = TaskResult(label, value=future.result())
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            result = TaskResult(label, error=exc)
        outcomes[future] = result
        if on_done is not None:
            on_done(result)

    return [outcomes[future] for _, future in submitted]
```

- [ ] **Step 4: Thread `on_done` through the titled-image helper**

In `scripts/non_ai/create_titled_images_short/create_titled_images_short.py`, replace `create_titled_images_for_items_short` with:

```python
def create_titled_images_for_items_short(
    items: Sequence[Item],
    *,
    on_done=None,
) -> list[TaskResult]:
    """Render every titled image. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, titled_image_jobs(items), on_done=on_done)
```

- [ ] **Step 5: Run the whole suite**

Run: `pytest -m "not slow" -v`
Expected: PASS — every existing test still passes, plus the two new ones.

- [ ] **Step 6: Commit**

```bash
git add utils/openai_support.py scripts/non_ai/create_titled_images_short/create_titled_images_short.py tests/test_openai_support.py
git commit -m "feat: report parallel job results as they complete"
```

---

### Task 2: Validation fixes that per-run overrides depend on

Two latent bugs block the config feature. `generate_list` calls `parse_items(content or "")`, and `parse_items`'s `expected_prompts` default is bound **at import time**, so overriding `IMAGE_PROMPTS_PER_ITEM` at runtime would validate against the stale value. Separately, `parse_items` accepts an empty `image_prompts` list (`all()` over an empty list is `True`), which later crashes the renderer.

**Files:**
- Modify: `models.py:91-99`
- Modify: `scripts/ai/generate_list/generate_list.py:131-133`
- Test: `tests/test_models.py`, `tests/test_generate_list.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_items` rejects empty prompt lists; `generate_list` honours the *current* value of `config.IMAGE_PROMPTS_PER_ITEM`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_parse_items_rejects_an_empty_image_prompt_list():
    from models import InvalidItemsError, parse_items

    payload = {"items": [{"title": "Dodo", "description": "A bird.", "image_prompts": []}]}
    with pytest.raises(InvalidItemsError, match="image_prompts"):
        parse_items(payload, expected_prompts=None)
```

Append to `tests/test_generate_list.py`:

```python
def test_generate_list_validates_against_the_current_prompt_count(monkeypatch):
    import config
    from scripts.ai.generate_list.generate_list import generate_list

    monkeypatch.setattr(config, "IMAGE_PROMPTS_PER_ITEM", 2)

    payload = json.dumps(
        {
            "items": [
                {
                    "title": "Dodo",
                    "description": "A bird.",
                    "image_prompts": ["one", "two"],
                }
            ]
        }
    )
    items = generate_list("birds", 1, client=FakeClient(payload))
    assert len(items[0].image_prompts) == 2
```

`tests/test_generate_list.py` already defines a fake client and imports `json`; reuse whatever name that file already uses instead of `FakeClient` if it differs. Read the file first and match it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py tests/test_generate_list.py -v`
Expected: FAIL — the empty-prompt test raises no error, and the prompt-count test fails with `item 1 needs exactly 3 image prompts, got 2`.

- [ ] **Step 3: Reject empty prompt lists**

In `models.py`, inside `parse_items`, replace the `prompts` validation block with:

```python
        prompts = payload.get("image_prompts")
        if (
            not isinstance(prompts, list)
            or not prompts
            or not all(isinstance(p, str) and p.strip() for p in prompts)
        ):
            raise InvalidItemsError(
                f"item {position} is missing a usable 'image_prompts' list"
            )
```

- [ ] **Step 4: Read the prompt count at call time**

In `scripts/ai/generate_list/generate_list.py`, change the last line of `generate_list` from `return parse_items(content or "")` to:

```python
    # Read the count now, not at import time, so a per-run override applies.
    return parse_items(content or "", expected_prompts=config.IMAGE_PROMPTS_PER_ITEM)
```

- [ ] **Step 5: Run the tests**

Run: `pytest -m "not slow" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add models.py scripts/ai/generate_list/generate_list.py tests/test_models.py tests/test_generate_list.py
git commit -m "fix: reject empty prompt lists and read prompt count at call time"
```

---

### Task 3: Split the pipeline into resumable stages

The UI must run stage 1, stop, let the user edit items, then continue. `run_pipeline` is currently one straight-line function, so extract each stage. `run_pipeline` keeps its exact signature, output and behaviour by composing them.

**Files:**
- Modify: `pipeline.py` (whole file)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `run_all(..., on_done=...)` and `create_titled_images_for_items_short(..., on_done=...)` from Task 1.
- Produces:
  - `Log = Callable[[str], None]`
  - `generate_items_stage(topic: str, num_items: int, *, client=None, log: Log = print) -> list[Item]`
  - `media_job_total(items: Sequence[Item]) -> int`
  - `titled_job_total(items: Sequence[Item]) -> int`
  - `generate_media_stage(items, *, client=None, log: Log = print, on_asset=None) -> None`
  - `render_titled_images_stage(items, *, log: Log = print, on_asset=None) -> None`
  - `render_video_stage(items, *, log: Log = print) -> Path`
  - `archive_stage(topic: str, items, *, log: Log = print) -> Path`
  - `run_pipeline(topic, num_items, *, client=None) -> Path` (unchanged signature)
  - `PipelineError`, `missing_media`, `missing_titled_images` (unchanged)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_media_job_total_counts_audio_plus_every_image():
    from pipeline import media_job_total

    items = [Item("A", "d", ("p1", "p2")), Item("B", "d", ("p1",))]
    # 2 narrations + 3 images
    assert media_job_total(items) == 5


def test_titled_job_total_counts_every_image():
    from pipeline import titled_job_total

    items = [Item("A", "d", ("p1", "p2")), Item("B", "d", ("p1",))]
    assert titled_job_total(items) == 3


def test_generate_items_stage_saves_the_list_and_logs(tmp_path, monkeypatch):
    import json

    from pipeline import generate_items_stage
    from utils.paths import list_items_path

    monkeypatch.chdir(tmp_path)

    def fake_generate_list(topic, num_items, *, client=None):
        return [Item("Dodo", "A bird.", ("a", "b", "c"))]

    monkeypatch.setattr("pipeline.generate_list", fake_generate_list)

    lines = []
    items = generate_items_stage("birds", 1, log=lines.append)

    assert [item.title for item in items] == ["Dodo"]
    saved = json.loads(list_items_path().read_text())
    assert saved["items"][0]["title"] == "Dodo"
    assert any("Dodo" in line for line in lines)


def test_generate_media_stage_raises_when_an_asset_is_missing(tmp_path, monkeypatch):
    from pipeline import PipelineError, generate_media_stage
    from utils.paths import ensure_output_dirs

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    monkeypatch.setattr("pipeline.image_jobs", lambda items, client=None: [])
    monkeypatch.setattr("pipeline.audio_jobs", lambda items, client=None: [])

    with pytest.raises(PipelineError, match="Media generation"):
        generate_media_stage(one_item(), log=lambda _: None)


def test_generate_media_stage_forwards_asset_results(tmp_path, monkeypatch):
    from pipeline import generate_media_stage

    monkeypatch.chdir(tmp_path)
    items = one_item()
    ensure_output_dirs()
    write_media(items)

    monkeypatch.setattr(
        "pipeline.image_jobs", lambda items, client=None: [("image 1", lambda: None)]
    )
    monkeypatch.setattr("pipeline.audio_jobs", lambda items, client=None: [])

    seen = []
    generate_media_stage(items, log=lambda _: None, on_asset=seen.append)
    assert [r.label for r in seen] == ["image 1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'media_job_total' from 'pipeline'`

- [ ] **Step 3: Rewrite `pipeline.py`**

Replace the entire file with:

```python
"""Stage orchestration for the video generation pipeline.

Each stage is callable on its own so a caller can stop between stages — the
web UI pauses after the list stage to let a human edit the items. `run_pipeline`
composes all five and is what the CLI uses.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Sequence

import config
from models import Item, save_items
from scripts.ai.generate_audios.generate_audio import audio_jobs
from scripts.ai.generate_images.generate_images import image_jobs
from scripts.ai.generate_list.generate_list import generate_list
from scripts.non_ai.create_titled_images_short.create_titled_images_short import (
    create_titled_images_for_items_short,
)
from scripts.non_ai.generate_video_short.generate_video_short import (
    generate_video_short,
)
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_to_generated_data,
)
from utils.openai_support import TaskResult, describe_failures, run_all
from utils.paths import (
    audio_path,
    ensure_output_dirs,
    image_path,
    list_items_path,
    titled_image_path,
)

TOTAL_STAGES = 5

Log = Callable[[str], None]
AssetCallback = Callable[[TaskResult], None]


class PipelineError(RuntimeError):
    """A stage produced incomplete output, so the pipeline cannot continue."""


def _unusable(path: Path) -> bool:
    """A file is unusable if it is absent or empty."""
    return not path.exists() or path.stat().st_size == 0


def missing_media(items: Sequence[Item]) -> list[Path]:
    """Every expected image and audio file that is absent or empty."""
    missing: list[Path] = []
    for item_number, item in enumerate(items, start=1):
        candidate = audio_path(item_number)
        if _unusable(candidate):
            missing.append(candidate)
        for prompt_number in range(1, len(item.image_prompts) + 1):
            candidate = image_path(item_number, prompt_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def missing_titled_images(items: Sequence[Item]) -> list[Path]:
    """Every expected titled image that is absent or empty."""
    missing: list[Path] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number in range(1, len(item.image_prompts) + 1):
            candidate = titled_image_path(item_number, prompt_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def _fail(stage: str, paths: Sequence[Path]) -> None:
    listing = "\n".join(f"  - {path}" for path in paths)
    raise PipelineError(
        f"{stage} did not produce {len(paths)} required file(s):\n{listing}\n"
        f"Fix the underlying errors above and re-run."
    )


def media_job_total(items: Sequence[Item]) -> int:
    """One narration per item plus one image per prompt."""
    return len(items) + sum(len(item.image_prompts) for item in items)


def titled_job_total(items: Sequence[Item]) -> int:
    """One titled frame per generated image."""
    return sum(len(item.image_prompts) for item in items)


def generate_items_stage(
    topic: str,
    num_items: int,
    *,
    client=None,
    log: Log = print,
) -> list[Item]:
    """Stage 1: ask the model for the item list and save it to disk."""
    ensure_output_dirs()
    log(f"Generating {num_items} items for '{topic}'...")
    items = generate_list(topic, num_items, client=client)
    save_items(items, list_items_path())
    for number, item in enumerate(items, start=1):
        log(f"  {number}. {item.title}")
    return items


def generate_media_stage(
    items: Sequence[Item],
    *,
    client=None,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 2: generate every image and narration, then verify all of them."""
    ensure_output_dirs()
    total = media_job_total(items)
    log(
        f"Generating {total} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    # One shared pool, so image and audio work interleaves under a single cap.
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        jobs = image_jobs(items, client=client) + audio_jobs(items, client=client)
        results = run_all(executor, jobs, on_done=on_asset)

    failures = describe_failures(results)
    if failures:
        log(failures)

    missing = missing_media(items)
    if missing:
        _fail("Media generation", missing)


def render_titled_images_stage(
    items: Sequence[Item],
    *,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 3: compose each image onto a blurred backdrop with its title."""
    log("Rendering titled images...")
    results = create_titled_images_for_items_short(items, on_done=on_asset)

    failures = describe_failures(results)
    if failures:
        log(failures)

    missing = missing_titled_images(items)
    if missing:
        _fail("Titled image rendering", missing)


def render_video_stage(items: Sequence[Item], *, log: Log = print) -> Path:
    """Stage 4: assemble the titled images and narration into the final video."""
    log("Assembling video...")
    return generate_video_short(items)


def archive_stage(topic: str, items: Sequence[Item], *, log: Log = print) -> Path:
    """Stage 5: copy the whole run into `generated_data/<topic-slug>/`."""
    log("Archiving...")
    return save_to_generated_data(topic, items)


def _banner(step: int) -> Log:
    """A logger that stamps a `[n/5]` banner onto the stage's first line only.

    Keeps the CLI's output byte-identical now that stages own their headlines.
    """
    pending = [True]

    def log(message: str) -> None:
        if pending[0]:
            pending[0] = False
            print(f"\n[{step}/{TOTAL_STAGES}] {message}")
        else:
            print(message)

    return log


def run_pipeline(topic: str, num_items: int, *, client=None) -> Path:
    """Run every stage end to end and return the path to the finished video."""
    ensure_output_dirs()

    items = generate_items_stage(topic, num_items, client=client, log=_banner(1))
    generate_media_stage(items, client=client, log=_banner(2))
    render_titled_images_stage(items, log=_banner(3))
    video = render_video_stage(items, log=_banner(4))
    archive_stage(topic, items, log=_banner(5))

    return video
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS — all pre-existing tests plus the five new ones.

- [ ] **Step 5: Verify the CLI still behaves**

Run: `python main.py --topic "" --items 0 2>&1 | head -5`
Expected: `--items must be at least 1, got 0` on stderr, exit code 2. This confirms the module still imports and `main.py` is wired up; it makes no API calls.

Then confirm the full suite: `pytest -m "not slow" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "refactor: split the pipeline into independently callable stages"
```

---

### Task 4: Config introspection and per-run overrides

The Config screen shows every `config.py` constant and lets a subset be overridden for one run. Overrides mutate the `config` module for the duration of the run — safe only because exactly one run executes at a time (see Global Constraints), and always restored in a `finally`.

**Files:**
- Create: `api/__init__.py`
- Create: `api/config_view.py`
- Test: `tests/api/__init__.py`, `tests/api/test_config_view.py`

**Interfaces:**
- Consumes: `config` module.
- Produces:
  - `OverridableField(name: str, type: str, choices: tuple[str, ...] | None, description: str)` — frozen dataclass
  - `OVERRIDABLE: tuple[OverridableField, ...]`
  - `effective_config() -> dict[str, Any]`
  - `ConfigOverrideError(ValueError)`
  - `validate_overrides(raw: dict[str, Any]) -> dict[str, Any]`
  - `apply_overrides(overrides: dict[str, Any])` — context manager

- [ ] **Step 1: Write the failing tests**

Create `tests/api/__init__.py` as an empty file, and `tests/api/test_config_view.py`:

```python
import pytest

import config
from api.config_view import (
    OVERRIDABLE,
    ConfigOverrideError,
    apply_overrides,
    effective_config,
    validate_overrides,
)


def test_effective_config_exposes_uppercase_constants():
    values = effective_config()
    assert values["VIDEO_WIDTH"] == 1080
    assert values["IMAGE_QUALITY"] == config.IMAGE_QUALITY
    assert "os" not in values


def test_effective_config_values_are_json_safe():
    for name, value in effective_config().items():
        assert isinstance(value, (str, int, float)), f"{name} is {type(value)}"


def test_every_overridable_field_names_a_real_constant():
    for field in OVERRIDABLE:
        assert hasattr(config, field.name)


def test_validate_overrides_coerces_integers():
    assert validate_overrides({"MAX_RETRIES": "7"}) == {"MAX_RETRIES": 7}


def test_validate_overrides_rejects_an_unknown_name():
    with pytest.raises(ConfigOverrideError, match="not overridable"):
        validate_overrides({"VIDEO_WIDTH": 720})


def test_validate_overrides_rejects_a_non_positive_integer():
    with pytest.raises(ConfigOverrideError, match="greater than zero"):
        validate_overrides({"MAX_RETRIES": 0})


def test_validate_overrides_rejects_a_value_outside_the_choices():
    with pytest.raises(ConfigOverrideError, match="must be one of"):
        validate_overrides({"IMAGE_QUALITY": "ultra"})


def test_apply_overrides_restores_the_previous_values():
    original = config.IMAGE_QUALITY
    with apply_overrides({"IMAGE_QUALITY": "low"}):
        assert config.IMAGE_QUALITY == "low"
    assert config.IMAGE_QUALITY == original


def test_apply_overrides_restores_after_an_exception():
    original = config.MAX_RETRIES
    with pytest.raises(RuntimeError):
        with apply_overrides({"MAX_RETRIES": 1}):
            raise RuntimeError("boom")
    assert config.MAX_RETRIES == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_config_view.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Create the package and the module**

Create `api/__init__.py` as an empty file. Create `api/config_view.py`:

```python
"""Expose pipeline configuration to the UI, and override it for one run.

`config.py` reads its values at import time, so a per-run override cannot be
done through the environment. Instead the run worker swaps the module
attributes for the duration of the run and puts them back afterwards. That is
only safe because exactly one run executes at a time.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import config


@dataclass(frozen=True)
class OverridableField:
    """One config constant the UI is allowed to change for a single run."""

    name: str
    type: str  # "int" or "str"
    choices: tuple[str, ...] | None = None
    description: str = ""


OVERRIDABLE: tuple[OverridableField, ...] = (
    OverridableField("TEXT_MODEL", "str", None, "Generates the item list."),
    OverridableField("TTS_MODEL", "str", None, "Generates the narration."),
    OverridableField("TTS_VOICE", "str", None, "Narration voice."),
    OverridableField("IMAGE_MODEL", "str", None, "Generates the images."),
    OverridableField("IMAGE_SIZE", "str", None, "Generated image dimensions."),
    OverridableField(
        "IMAGE_QUALITY",
        "str",
        ("low", "medium", "high"),
        "Higher costs more and takes longer.",
    ),
    OverridableField(
        "IMAGE_PROMPTS_PER_ITEM", "int", None, "Images generated for each item."
    ),
    OverridableField(
        "MAX_CONCURRENT_REQUESTS", "int", None, "Parallel OpenAI calls."
    ),
    OverridableField("MAX_RETRIES", "int", None, "Attempts per call."),
    OverridableField("VIDEO_FPS", "int", None, "Frames per second."),
    OverridableField(
        "VIDEO_PRESET",
        "str",
        ("ultrafast", "veryfast", "fast", "medium", "slow"),
        "x264 preset. Faster presets render quicker at a larger file size.",
    ),
)

_BY_NAME = {field.name: field for field in OVERRIDABLE}


class ConfigOverrideError(ValueError):
    """A requested override names an unknown constant or an invalid value."""


def effective_config() -> dict[str, Any]:
    """Every config constant currently in force, newest overrides included."""
    return {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper() and not name.startswith("_")
    }


def _clean_int(field: OverridableField, value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigOverrideError(
            f"{field.name} must be a whole number, got {value!r}"
        ) from exc
    if number <= 0:
        raise ConfigOverrideError(
            f"{field.name} must be greater than zero, got {number}"
        )
    return number


def _clean_str(field: OverridableField, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigOverrideError(f"{field.name} must be a non-empty string")
    text = value.strip()
    if field.choices and text not in field.choices:
        raise ConfigOverrideError(
            f"{field.name} must be one of {', '.join(field.choices)}, got {text!r}"
        )
    return text


def validate_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce and check a raw override map, or raise `ConfigOverrideError`."""
    cleaned: dict[str, Any] = {}
    for name, value in raw.items():
        field = _BY_NAME.get(name)
        if field is None:
            raise ConfigOverrideError(f"{name} is not overridable")
        cleaned[name] = (
            _clean_int(field, value)
            if field.type == "int"
            else _clean_str(field, value)
        )
    return cleaned


@contextmanager
def apply_overrides(overrides: dict[str, Any]) -> Iterator[None]:
    """Swap config constants for the duration of the block, then restore them."""
    previous = {name: getattr(config, name) for name in overrides}
    for name, value in overrides.items():
        setattr(config, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(config, name, value)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/api/test_config_view.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add api/__init__.py api/config_view.py tests/api/
git commit -m "feat: expose pipeline config and per-run overrides"
```

---

### Task 5: The run store and background worker

The heart of the backend: a state machine that runs the five stages on a thread, records progress, and blocks at `awaiting_review` until the UI approves the items.

**State machine.** `pending` → `generating_list` → (`awaiting_review` only when review was requested) → `generating_media` → `rendering_titles` → `rendering_video` → `archiving` → `completed`. Any state can move to `failed` or `cancelled`. `completed`, `failed` and `cancelled` are terminal.

**Files:**
- Create: `api/runs.py`
- Test: `tests/api/test_runs.py`

**Interfaces:**
- Consumes: `pipeline.generate_items_stage`, `generate_media_stage`, `render_titled_images_stage`, `render_video_stage`, `archive_stage`, `media_job_total`, `titled_job_total` (Task 3); `api.config_view.apply_overrides` (Task 4).
- Produces:
  - `TERMINAL_STATUSES: frozenset[str]`
  - `AssetStatus(label: str, ok: bool, error: str | None)` — dataclass
  - `Run` — dataclass with `id, topic, num_items, review_items, overrides, status, created_at, finished_at, items, assets, asset_total, logs, error, video_path, archive_slug`
  - `RunConflictError(RuntimeError)`, `RunNotFoundError(KeyError)`
  - `RunStore(client=None)` with `.start(topic, num_items, review_items, overrides) -> Run`, `.get(run_id) -> Run`, `.list() -> list[Run]`, `.approve_items(run_id, items) -> Run`, `.cancel(run_id) -> Run`, `.wait_for_idle(timeout=...)` (tests only)

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_runs.py`:

```python
import pytest

from api.runs import RunConflictError, RunNotFoundError, RunStore
from models import Item
from utils.paths import audio_path, ensure_output_dirs, image_path, titled_image_path


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def stub_stages(monkeypatch, *, items=None):
    """Replace every pipeline stage with a fast, side-effect-free fake."""
    produced = items if items is not None else one_item()

    monkeypatch.setattr(
        "api.runs.pipeline.generate_items_stage",
        lambda topic, num_items, client=None, log=print: produced,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_media_stage",
        lambda items, client=None, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_titled_images_stage",
        lambda items, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_video_stage",
        lambda items, log=print: __import__("pathlib").Path("outputs/video_output/final_video_short.mp4"),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.archive_stage",
        lambda topic, items, log=print: __import__("pathlib").Path("generated_data/birds"),
    )


def test_a_run_without_review_completes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert finished.error is None
    assert [item.title for item in finished.items] == ["Dodo"]
    assert finished.archive_slug == "birds"
    assert finished.finished_at is not None


def test_a_review_run_pauses_until_items_are_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    assert store.get(run.id).status == "awaiting_review"

    edited = [Item("Moa", "A taller bird.", ("x", "y"))]
    store.approve_items(run.id, edited)
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert [item.title for item in finished.items] == ["Moa"]


def test_starting_a_second_run_while_one_is_active_conflicts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    first = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(first.id, "awaiting_review")

    with pytest.raises(RunConflictError):
        store.start("Fish", 1, review_items=False, overrides={})


def test_a_failing_stage_marks_the_run_failed(tmp_path, monkeypatch):
    from pipeline import PipelineError

    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    def boom(items, client=None, log=print, on_asset=None):
        raise PipelineError("no images")

    monkeypatch.setattr("api.runs.pipeline.generate_media_stage", boom)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert "no images" in finished.error


def test_cancelling_while_awaiting_review_ends_the_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    store.cancel(run.id)
    store.wait_for_idle()

    assert store.get(run.id).status == "cancelled"


def test_approving_a_run_that_is_not_awaiting_review_conflicts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    with pytest.raises(RunConflictError):
        store.approve_items(run.id, one_item())


def test_get_raises_for_an_unknown_run():
    with pytest.raises(RunNotFoundError):
        RunStore().get("nope")


def test_overrides_apply_only_while_the_run_executes(tmp_path, monkeypatch):
    import config

    monkeypatch.chdir(tmp_path)
    original = config.IMAGE_QUALITY
    seen = []

    def record(topic, num_items, client=None, log=print):
        seen.append(config.IMAGE_QUALITY)
        return one_item()

    stub_stages(monkeypatch)
    monkeypatch.setattr("api.runs.pipeline.generate_items_stage", record)

    store = RunStore()
    store.start("Birds", 1, review_items=False, overrides={"IMAGE_QUALITY": "low"})
    store.wait_for_idle()

    assert seen == ["low"]
    assert config.IMAGE_QUALITY == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_runs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.runs'`

- [ ] **Step 3: Write `api/runs.py`**

```python
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
from typing import Any, Sequence

import pipeline
from api.config_view import apply_overrides
from models import Item, save_items
from utils.openai_support import TaskResult
from utils.paths import list_items_path, slugify

STATUS_PENDING = "pending"
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
    num_items: int
    review_items: bool
    overrides: dict[str, Any]
    status: str = STATUS_PENDING
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    items: list[Item] = field(default_factory=list)
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
        num_items: int,
        *,
        review_items: bool,
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
                num_items=num_items,
                review_items=review_items,
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

    def approve_items(self, run_id: str, items: Sequence[Item]) -> Run:
        """Replace the run's items with the edited ones and let it continue."""
        with self._lock:
            run = self.get(run_id)
            if run.status != STATUS_AWAITING_REVIEW:
                raise RunConflictError(
                    f"run {run_id} is {run.status}, not {STATUS_AWAITING_REVIEW}"
                )
            run.items = list(items)
            gate = self._gates[run_id]

        # Overwrite the saved list so the archive reflects the edits.
        save_items(run.items, list_items_path())
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

    def wait_for_status(
        self, run_id: str, status: str, timeout: float = 10.0
    ) -> Run:
        """Block until the run reaches `status`. Used by tests."""
        deadline = threading.Event()
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
            deadline.wait(step)
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
            error=None if result.ok else f"{type(result.error).__name__}: {result.error}",
        )
        with self._lock:
            run.assets.append(status)

    def _check_cancelled(self, gate: _Gate) -> None:
        if gate.cancel.is_set():
            raise _Cancelled()

    def _execute(self, run: Run) -> None:
        gate = self._gates[run.id]
        log = lambda message: self._log(run, message)  # noqa: E731

        try:
            with apply_overrides(run.overrides):
                self._check_cancelled(gate)
                self._set_status(run, "generating_list")
                items = pipeline.generate_items_stage(
                    run.topic, run.num_items, client=self._client, log=log
                )
                with self._lock:
                    run.items = list(items)

                if run.review_items:
                    self._set_status(run, STATUS_AWAITING_REVIEW)
                    log("Waiting for you to review the items...")
                    gate.review.wait()
                    self._check_cancelled(gate)
                    with self._lock:
                        items = list(run.items)
                    log(f"Continuing with {len(items)} approved item(s).")

                self._check_cancelled(gate)
                self._set_status(run, "generating_media")
                self._begin_asset_stage(run, pipeline.media_job_total(items))
                pipeline.generate_media_stage(
                    items,
                    client=self._client,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "rendering_titles")
                self._begin_asset_stage(run, pipeline.titled_job_total(items))
                pipeline.render_titled_images_stage(
                    items,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "rendering_video")
                self._begin_asset_stage(run, 0)
                video = pipeline.render_video_stage(items, log=log)
                with self._lock:
                    run.video_path = video

                self._check_cancelled(gate)
                self._set_status(run, "archiving")
                pipeline.archive_stage(run.topic, items, log=log)
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
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/api/test_runs.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add api/runs.py tests/api/test_runs.py
git commit -m "feat: add the run state machine and background worker"
```

---

### Task 6: Archive reader

Reads `generated_data/` for the archive browser. Must tolerate the four archives already on disk, which predate `titled_images/` and the archived video — do not assume any subdirectory exists.

**Files:**
- Create: `api/archives.py`
- Test: `tests/api/test_archives.py`

**Interfaces:**
- Consumes: `utils.paths.GENERATED_DATA_ROOT`, `models.load_items`.
- Produces:
  - `MEDIA_PREFIX = "/media/generated_data"`
  - `ArchiveNotFoundError(KeyError)`
  - `list_archives() -> list[dict[str, Any]]` — keys `slug, item_count, image_count, audio_count, has_video, modified_at`
  - `archive_detail(slug: str) -> dict[str, Any]` — keys `slug, video_url, items`; each item has `title, description, image_prompts, image_urls, titled_image_urls, audio_url`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_archives.py`:

```python
import json

import pytest

from api.archives import ArchiveNotFoundError, archive_detail, list_archives


def build_archive(root, slug, *, with_titled=True, with_video=True):
    folder = root / "generated_data" / slug
    (folder / "images").mkdir(parents=True)
    (folder / "audio").mkdir(parents=True)
    (folder / "list_items.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Dodo",
                        "description": "A bird.",
                        "image_prompts": ["a", "b"],
                    }
                ]
            }
        )
    )
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"x")
    (folder / "images" / "item_01_prompt_02.png").write_bytes(b"x")
    (folder / "audio" / "item_01.mp3").write_bytes(b"x")
    if with_titled:
        (folder / "titled_images").mkdir()
        (folder / "titled_images" / "item_01_prompt_01_short.png").write_bytes(b"x")
    if with_video:
        (folder / "final_video_short.mp4").write_bytes(b"x")
    return folder


def test_list_archives_summarises_each_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")

    (summary,) = list_archives()
    assert summary["slug"] == "birds"
    assert summary["item_count"] == 1
    assert summary["image_count"] == 2
    assert summary["audio_count"] == 1
    assert summary["has_video"] is True
    assert summary["modified_at"]


def test_list_archives_is_empty_when_there_is_no_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert list_archives() == []


def test_archive_detail_builds_media_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")

    detail = archive_detail("birds")
    assert detail["video_url"] == "/media/generated_data/birds/final_video_short.mp4"

    (item,) = detail["items"]
    assert item["title"] == "Dodo"
    assert item["image_urls"] == [
        "/media/generated_data/birds/images/item_01_prompt_01.png",
        "/media/generated_data/birds/images/item_01_prompt_02.png",
    ]
    assert item["titled_image_urls"] == [
        "/media/generated_data/birds/titled_images/item_01_prompt_01_short.png"
    ]
    assert item["audio_url"] == "/media/generated_data/birds/audio/item_01.mp3"


def test_archive_detail_tolerates_an_older_archive(tmp_path, monkeypatch):
    # The archives already on disk have no titled_images/ and no video.
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "old", with_titled=False, with_video=False)

    detail = archive_detail("old")
    assert detail["video_url"] is None
    assert detail["items"][0]["titled_image_urls"] == []


def test_archive_detail_rejects_an_unknown_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ArchiveNotFoundError):
        archive_detail("missing")


@pytest.mark.parametrize("slug", ["../secrets", "birds/../..", "a b", "Birds"])
def test_archive_detail_rejects_a_malformed_slug(tmp_path, monkeypatch, slug):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")
    with pytest.raises(ArchiveNotFoundError):
        archive_detail(slug)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_archives.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.archives'`

- [ ] **Step 3: Write `api/archives.py`**

```python
"""Read `generated_data/` into payloads the archive browser can render.

Filenames are the join key: `images/item_04_prompt_02.png` belongs to item 4.
Older archives were written before titled images and the video were copied in,
so every subdirectory is treated as optional.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import InvalidItemsError, load_items
from utils.paths import (
    ARCHIVED_LIST_FILENAME,
    GENERATED_DATA_ROOT,
    VIDEO_FILENAME,
)

MEDIA_PREFIX = "/media/generated_data"

# `slugify` only ever emits lowercase alphanumerics and underscores. Anything
# else is either a stray directory or a traversal attempt.
_VALID_SLUG = re.compile(r"^[a-z0-9_]+$")


class ArchiveNotFoundError(KeyError):
    """No readable archive with that slug exists."""


def _url(slug: str, *parts: str) -> str:
    return "/".join((MEDIA_PREFIX, slug, *parts))


def _modified_at(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return stamp.isoformat()


def _count_files(directory: Path, suffix: str) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for entry in directory.iterdir() if entry.suffix == suffix)


def _names_for_item(directory: Path, item_number: int, suffix: str) -> list[str]:
    if not directory.is_dir():
        return []
    prefix = f"item_{item_number:02d}_"
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix == suffix and entry.name.startswith(prefix)
    )


def _archive_dir(slug: str) -> Path:
    if not _VALID_SLUG.match(slug):
        raise ArchiveNotFoundError(slug)
    folder = GENERATED_DATA_ROOT / slug
    if not folder.is_dir():
        raise ArchiveNotFoundError(slug)
    return folder


def list_archives() -> list[dict[str, Any]]:
    """Summarise every archive folder, newest first."""
    if not GENERATED_DATA_ROOT.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for folder in GENERATED_DATA_ROOT.iterdir():
        if not folder.is_dir() or not _VALID_SLUG.match(folder.name):
            continue
        listing = folder / ARCHIVED_LIST_FILENAME
        try:
            items = load_items(listing) if listing.is_file() else []
        except (InvalidItemsError, OSError):
            items = []
        summaries.append(
            {
                "slug": folder.name,
                "item_count": len(items),
                "image_count": _count_files(folder / "images", ".png"),
                "audio_count": _count_files(folder / "audio", ".mp3"),
                "has_video": (folder / VIDEO_FILENAME).is_file(),
                "modified_at": _modified_at(folder),
            }
        )

    summaries.sort(key=lambda summary: summary["modified_at"], reverse=True)
    return summaries


def archive_detail(slug: str) -> dict[str, Any]:
    """One archive's items with a media URL for every file that exists."""
    folder = _archive_dir(slug)

    listing = folder / ARCHIVED_LIST_FILENAME
    if not listing.is_file():
        raise ArchiveNotFoundError(slug)
    try:
        items = load_items(listing)
    except (InvalidItemsError, OSError) as exc:
        raise ArchiveNotFoundError(slug) from exc

    payload_items: list[dict[str, Any]] = []
    for item_number, item in enumerate(items, start=1):
        audio_name = f"item_{item_number:02d}.mp3"
        has_audio = (folder / "audio" / audio_name).is_file()
        payload_items.append(
            {
                "title": item.title,
                "description": item.description,
                "image_prompts": list(item.image_prompts),
                "image_urls": [
                    _url(slug, "images", name)
                    for name in _names_for_item(folder / "images", item_number, ".png")
                ],
                "titled_image_urls": [
                    _url(slug, "titled_images", name)
                    for name in _names_for_item(
                        folder / "titled_images", item_number, ".png"
                    )
                ],
                "audio_url": _url(slug, "audio", audio_name) if has_audio else None,
            }
        )

    video = folder / VIDEO_FILENAME
    return {
        "slug": slug,
        "video_url": _url(slug, VIDEO_FILENAME) if video.is_file() else None,
        "items": payload_items,
    }
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/api/test_archives.py -v`
Expected: PASS (9 tests, four of them parametrized)

- [ ] **Step 5: Sanity-check against the real archives**

Run: `python -c "from api.archives import list_archives, archive_detail; a = list_archives(); print(a); print(archive_detail(a[0]['slug'])['items'][0]['image_urls'][:2])"`
Expected: four summaries printed, then two `/media/generated_data/...` URLs. No exception.

- [ ] **Step 6: Commit**

```bash
git add api/archives.py tests/api/test_archives.py
git commit -m "feat: read generated_data archives for the browser"
```

---

### Task 7: The HTTP API

Wire the store, config view and archive reader to HTTP. The wire contract defined in `api/schemas.py` here is mirrored exactly by `frontend/src/lib/types.ts` in Task 8 — keep the two in sync.

**Endpoints:**

| Method | Path | Body | Returns | Errors |
|---|---|---|---|---|
| GET | `/api/health` | — | `{"status": "ok"}` | — |
| GET | `/api/config` | — | `ConfigPayload` | — |
| GET | `/api/runs` | — | `RunSummaryPayload[]` | — |
| POST | `/api/runs` | `CreateRunRequest` | `RunDetailPayload` | 400 bad override, 409 run active |
| GET | `/api/runs/{run_id}` | — | `RunDetailPayload` | 404 |
| POST | `/api/runs/{run_id}/items` | `ApproveItemsRequest` | `RunDetailPayload` | 400 invalid items, 404, 409 not awaiting review |
| POST | `/api/runs/{run_id}/cancel` | — | `RunDetailPayload` | 404, 409 already terminal |
| GET | `/api/archives` | — | `ArchiveSummaryPayload[]` | — |
| GET | `/api/archives/{slug}` | — | `ArchiveDetailPayload` | 404 |

**Files:**
- Create: `api/schemas.py`, `api/app.py`, `api/routes.py`
- Modify: `requirements.txt`
- Test: `tests/api/test_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 4, 5 and 6.
- Produces: `create_app(*, client=None) -> FastAPI`, module-level `app`, and the schema classes listed above.

- [ ] **Step 1: Add the dependencies**

Append to `requirements.txt`:

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0
```

Run: `pip install -r requirements.txt`
Expected: fastapi, uvicorn, httpx and pydantic installed.

- [ ] **Step 2: Write the failing tests**

Create `tests/api/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from models import Item


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def stub_stages(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(
        "api.runs.pipeline.generate_items_stage",
        lambda topic, num_items, client=None, log=print: one_item(),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_media_stage",
        lambda items, client=None, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_titled_images_stage",
        lambda items, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_video_stage",
        lambda items, log=print: Path("outputs/video_output/final_video_short.mp4"),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.archive_stage",
        lambda topic, items, log=print: Path("generated_data/birds"),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_lists_values_and_overridable_fields(client):
    payload = client.get("/api/config").json()
    assert payload["values"]["VIDEO_WIDTH"] == 1080
    names = [field["name"] for field in payload["overridable"]]
    assert "IMAGE_QUALITY" in names
    quality = next(f for f in payload["overridable"] if f["name"] == "IMAGE_QUALITY")
    assert quality["choices"] == ["low", "medium", "high"]


def test_creating_a_run_returns_it(client, monkeypatch):
    stub_stages(monkeypatch)
    response = client.post("/api/runs", json={"topic": "Birds", "num_items": 1})
    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "Birds"
    assert body["id"]


def test_creating_a_run_rejects_a_blank_topic(client):
    response = client.post("/api/runs", json={"topic": "   ", "num_items": 1})
    assert response.status_code == 422


def test_creating_a_run_rejects_a_bad_override(client):
    response = client.post(
        "/api/runs",
        json={"topic": "Birds", "num_items": 1, "overrides": {"VIDEO_WIDTH": 720}},
    )
    assert response.status_code == 400
    assert "not overridable" in response.json()["detail"]


def test_a_second_run_conflicts(client, monkeypatch):
    stub_stages(monkeypatch)
    client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    )
    client.app.state.run_store.wait_for_status(
        client.app.state.run_store.list()[0].id, "awaiting_review"
    )
    second = client.post("/api/runs", json={"topic": "Fish", "num_items": 1})
    assert second.status_code == 409


def test_getting_an_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_approving_items_resumes_the_run(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    store = client.app.state.run_store
    store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/items",
        json={
            "items": [
                {"title": "Moa", "description": "Taller.", "image_prompts": ["x"]}
            ]
        },
    )
    assert response.status_code == 200

    store.wait_for_idle()
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert detail["status"] == "completed"
    assert detail["items"][0]["title"] == "Moa"
    assert detail["video_url"].startswith("/media/outputs/video_output/")


def test_approving_items_rejects_an_item_with_no_prompts(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    client.app.state.run_store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/items",
        json={"items": [{"title": "Moa", "description": "d", "image_prompts": []}]},
    )
    assert response.status_code == 400


def test_cancelling_a_run(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    store = client.app.state.run_store
    store.wait_for_status(created["id"], "awaiting_review")

    assert client.post(f"/api/runs/{created['id']}/cancel").status_code == 200
    store.wait_for_idle()
    assert client.get(f"/api/runs/{created['id']}").json()["status"] == "cancelled"


def test_archives_are_listed_and_readable(client, tmp_path):
    import json

    folder = tmp_path / "generated_data" / "birds"
    (folder / "images").mkdir(parents=True)
    (folder / "list_items.json").write_text(
        json.dumps(
            {"items": [{"title": "Dodo", "description": "d", "image_prompts": ["a"]}]}
        )
    )
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"x")

    listing = client.get("/api/archives").json()
    assert [entry["slug"] for entry in listing] == ["birds"]

    detail = client.get("/api/archives/birds").json()
    assert detail["items"][0]["title"] == "Dodo"
    assert client.get("/api/archives/missing").status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/api/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.app'`

- [ ] **Step 4: Write `api/schemas.py`**

```python
"""The HTTP wire contract.

`frontend/src/lib/types.ts` mirrors this file field for field. Change both
together.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from api.config_view import OVERRIDABLE, effective_config
from api.runs import Run
from models import Item


class ItemPayload(BaseModel):
    title: str
    description: str
    image_prompts: list[str]

    @classmethod
    def from_item(cls, item: Item) -> "ItemPayload":
        return cls(
            title=item.title,
            description=item.description,
            image_prompts=list(item.image_prompts),
        )


class AssetStatusPayload(BaseModel):
    label: str
    ok: bool
    error: str | None = None


class RunSummaryPayload(BaseModel):
    id: str
    topic: str
    num_items: int
    status: str
    created_at: str
    finished_at: str | None = None


class RunDetailPayload(RunSummaryPayload):
    review_items: bool
    overrides: dict[str, Any]
    items: list[ItemPayload]
    assets: list[AssetStatusPayload]
    asset_total: int
    logs: list[str]
    error: str | None = None
    video_url: str | None = None
    archive_slug: str | None = None


class CreateRunRequest(BaseModel):
    topic: str
    num_items: int = Field(ge=1, le=50)
    review_items: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def topic_is_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("topic must not be blank")
        return text


class ApproveItemsRequest(BaseModel):
    items: list[ItemPayload] = Field(min_length=1)


class ConfigFieldPayload(BaseModel):
    name: str
    type: str
    choices: list[str] | None = None
    description: str = ""


class ConfigPayload(BaseModel):
    values: dict[str, Any]
    overridable: list[ConfigFieldPayload]


class ArchiveSummaryPayload(BaseModel):
    slug: str
    item_count: int
    image_count: int
    audio_count: int
    has_video: bool
    modified_at: str


class ArchiveItemPayload(BaseModel):
    title: str
    description: str
    image_prompts: list[str]
    image_urls: list[str]
    titled_image_urls: list[str]
    audio_url: str | None = None


class ArchiveDetailPayload(BaseModel):
    slug: str
    video_url: str | None = None
    items: list[ArchiveItemPayload]


def config_payload() -> ConfigPayload:
    return ConfigPayload(
        values=effective_config(),
        overridable=[
            ConfigFieldPayload(
                name=field.name,
                type=field.type,
                choices=list(field.choices) if field.choices else None,
                description=field.description,
            )
            for field in OVERRIDABLE
        ],
    )


def run_summary(run: Run) -> RunSummaryPayload:
    return RunSummaryPayload(
        id=run.id,
        topic=run.topic,
        num_items=run.num_items,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def run_detail(run: Run) -> RunDetailPayload:
    """Build the full payload, including a cache-busted video URL.

    The rendered video always lands at the same path, so without the run id
    query the browser would replay the previous run's video.
    """
    video_url = None
    if run.video_path is not None and run.video_path.is_file():
        video_url = f"/media/{run.video_path.as_posix()}?run={run.id}"

    return RunDetailPayload(
        **run_summary(run).model_dump(),
        review_items=run.review_items,
        overrides=run.overrides,
        items=[ItemPayload.from_item(item) for item in run.items],
        assets=[
            AssetStatusPayload(label=asset.label, ok=asset.ok, error=asset.error)
            for asset in run.assets
        ],
        asset_total=run.asset_total,
        logs=list(run.logs),
        error=run.error,
        video_url=video_url,
        archive_slug=run.archive_slug,
    )
```

- [ ] **Step 5: Write `api/routes.py`**

```python
"""Every HTTP endpoint. Translates domain errors into status codes only."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api import archives, schemas
from api.config_view import ConfigOverrideError, validate_overrides
from api.runs import RunConflictError, RunNotFoundError, RunStore
from models import InvalidItemsError, parse_items

router = APIRouter()


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", response_model=schemas.ConfigPayload)
def read_config() -> schemas.ConfigPayload:
    return schemas.config_payload()


@router.get("/runs", response_model=list[schemas.RunSummaryPayload])
def list_runs(store: RunStore = Depends(get_store)):
    return [schemas.run_summary(run) for run in store.list()]


@router.post(
    "/runs",
    response_model=schemas.RunDetailPayload,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    payload: schemas.CreateRunRequest, store: RunStore = Depends(get_store)
):
    try:
        overrides: dict[str, Any] = validate_overrides(payload.overrides)
    except ConfigOverrideError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        run = store.start(
            payload.topic,
            payload.num_items,
            review_items=payload.review_items,
            overrides=overrides,
        )
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return schemas.run_detail(run)


@router.get("/runs/{run_id}", response_model=schemas.RunDetailPayload)
def read_run(run_id: str, store: RunStore = Depends(get_store)):
    try:
        return schemas.run_detail(store.get(run_id))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc


@router.post("/runs/{run_id}/items", response_model=schemas.RunDetailPayload)
def approve_items(
    run_id: str,
    payload: schemas.ApproveItemsRequest,
    store: RunStore = Depends(get_store),
):
    # Reuse the pipeline's own validation so the UI cannot submit an item the
    # renderer would choke on. The prompt count is free-form here: the user may
    # legitimately add or remove prompts while reviewing.
    try:
        items = parse_items(
            [item.model_dump() for item in payload.items], expected_prompts=None
        )
    except InvalidItemsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        return schemas.run_detail(store.approve_items(run_id, items))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=schemas.RunDetailPayload)
def cancel_run(run_id: str, store: RunStore = Depends(get_store)):
    try:
        return schemas.run_detail(store.cancel(run_id))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/archives", response_model=list[schemas.ArchiveSummaryPayload])
def list_archives():
    return archives.list_archives()


@router.get("/archives/{slug}", response_model=schemas.ArchiveDetailPayload)
def read_archive(slug: str):
    try:
        return archives.archive_detail(slug)
    except archives.ArchiveNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no archive {slug}"
        ) from exc
```

- [ ] **Step 6: Write `api/app.py`**

```python
"""FastAPI application factory.

Must be started from the repository root: every path in `utils.paths` is
relative to the current working directory by design, so the static mounts and
the pipeline both resolve against the CWD.

    uvicorn api.app:app --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.runs import RunStore
from utils.paths import GENERATED_DATA_ROOT, OUTPUTS_ROOT, ensure_output_dirs

# The Vite dev server runs on a different origin during development.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

FRONTEND_DIST = Path("frontend/dist")


def create_app(*, client=None) -> FastAPI:
    """Build an app rooted at the current working directory.

    A factory rather than a module-level singleton so tests can `chdir` into a
    temp directory first and inject a fake OpenAI client.
    """
    ensure_output_dirs()
    GENERATED_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Auto YouTube Generator", version="1.0.0")
    app.state.run_store = RunStore(client=client)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    # Mounted after the router so /api always wins.
    app.mount(
        "/media/outputs", StaticFiles(directory=OUTPUTS_ROOT), name="media-outputs"
    )
    app.mount(
        "/media/generated_data",
        StaticFiles(directory=GENERATED_DATA_ROOT),
        name="media-archives",
    )

    # Optional: serve a production frontend build if one has been made.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"
        )

    return app


app = create_app()
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/api/test_routes.py -v`
Expected: PASS (11 tests)

Then the whole suite: `pytest -m "not slow" -v`
Expected: PASS

- [ ] **Step 8: Smoke-test the live server**

Run in one terminal: `uvicorn api.app:app --port 8000`
In another: `curl -s localhost:8000/api/health && curl -s localhost:8000/api/archives | head -c 300`
Expected: `{"status":"ok"}` then a JSON array containing the four real archive slugs. Stop the server afterwards.

- [ ] **Step 9: Commit**

```bash
git add api/schemas.py api/routes.py api/app.py requirements.txt tests/api/test_routes.py
git commit -m "feat: expose the pipeline over an HTTP API"
```

---

### Task 8: Frontend scaffold, types and API client

Scaffold the SPA and build the typed client. Nothing renders yet beyond a placeholder — this task's deliverable is a running dev server, shadcn installed, and a tested API client.

**Files:**
- Create: `frontend/` (Vite scaffold), `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `frontend/src/setupTests.ts`
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/src/index.css`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the endpoints from Task 7.
- Produces: `ApiError`, and `getConfig, listRuns, createRun, getRun, approveItems, cancelRun, listArchives, getArchive`, plus the types `RunStatus, ItemPayload, AssetStatus, RunSummary, RunDetail, ConfigField, ConfigPayload, ArchiveSummary, ArchiveItem, ArchiveDetail, CreateRunRequest, TERMINAL_STATUSES, STAGE_SEQUENCE`.

- [ ] **Step 1: Scaffold Vite**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom
npm install -D @types/node
npm install tailwindcss @tailwindcss/vite
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: Configure Vite, Tailwind, the proxy and the path alias**

Replace `frontend/vite.config.ts` with:

```ts
/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
```

Replace the contents of `frontend/src/index.css` with a single line:

```css
@import "tailwindcss";
```

Add the path alias to **both** `frontend/tsconfig.json` and `frontend/tsconfig.app.json`, inside `compilerOptions` (create the `compilerOptions` block in `tsconfig.json` if the template left it out):

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

Create `frontend/src/setupTests.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Add a test script to `frontend/package.json`'s `scripts`:

```json
"test": "vitest run"
```

- [ ] **Step 3: Install shadcn/ui and the components this app uses**

```bash
npx shadcn@latest init
```

Accept the defaults; choose **Neutral** as the base color when prompted. This creates `components.json` and `src/lib/utils.ts`, and rewrites `src/index.css` with the shadcn theme variables. Then:

```bash
npx shadcn@latest add button card checkbox input label textarea badge progress select separator alert table
```

Verify: `ls src/components/ui` lists `button.tsx`, `card.tsx`, `checkbox.tsx`, `input.tsx`, `label.tsx`, `textarea.tsx`, `badge.tsx`, `progress.tsx`, `select.tsx`, `separator.tsx`, `alert.tsx`, `table.tsx`.

- [ ] **Step 4: Ignore frontend build artifacts**

Append to the repo-root `.gitignore`:

```
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 5: Write the failing API-client test**

Create `frontend/src/lib/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, approveItems, createRun, getRun, listArchives } from "./api";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("posts a new run to /api/runs", async () => {
    const fetchMock = mockFetch(201, { id: "abc", topic: "Birds" });
    const run = await createRun({ topic: "Birds", num_items: 3, review_items: true, overrides: {} });

    expect(run.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
    });
  });

  it("gets one run by id", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await getRun("abc");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/runs/abc");
  });

  it("wraps the server's detail message in an ApiError", async () => {
    mockFetch(409, { detail: "run abc is still generating_media" });
    await expect(getRun("abc")).rejects.toThrowError(ApiError);
    await expect(getRun("abc")).rejects.toThrow("run abc is still generating_media");
  });

  it("sends approved items under an items key", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await approveItems("abc", [
      { title: "Moa", description: "d", image_prompts: ["x"] },
    ]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      items: [{ title: "Moa", description: "d", image_prompts: ["x"] }],
    });
  });

  it("lists archives", async () => {
    const fetchMock = mockFetch(200, []);
    expect(await listArchives()).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/archives");
  });
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./api"`

- [ ] **Step 7: Write `frontend/src/lib/types.ts`**

```ts
// Mirrors api/schemas.py field for field. Change both together.

export type RunStatus =
  | "pending"
  | "generating_list"
  | "awaiting_review"
  | "generating_media"
  | "rendering_titles"
  | "rendering_video"
  | "archiving"
  | "completed"
  | "failed"
  | "cancelled";

/** Statuses after which polling should stop. Mirrors api.runs.TERMINAL_STATUSES. */
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

/** The stages shown in the progress indicator, in order. */
export const STAGE_SEQUENCE: readonly { status: RunStatus; label: string }[] = [
  { status: "generating_list", label: "Generate list" },
  { status: "awaiting_review", label: "Review items" },
  { status: "generating_media", label: "Images & audio" },
  { status: "rendering_titles", label: "Titled images" },
  { status: "rendering_video", label: "Render video" },
  { status: "archiving", label: "Archive" },
];

export interface ItemPayload {
  title: string;
  description: string;
  image_prompts: string[];
}

export interface AssetStatus {
  label: string;
  ok: boolean;
  error: string | null;
}

export interface RunSummary {
  id: string;
  topic: string;
  num_items: number;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  review_items: boolean;
  overrides: Record<string, string | number>;
  items: ItemPayload[];
  assets: AssetStatus[];
  asset_total: number;
  logs: string[];
  error: string | null;
  video_url: string | null;
  archive_slug: string | null;
}

export interface CreateRunRequest {
  topic: string;
  num_items: number;
  review_items: boolean;
  overrides: Record<string, string | number>;
}

export interface ConfigField {
  name: string;
  type: "int" | "str";
  choices: string[] | null;
  description: string;
}

export interface ConfigPayload {
  values: Record<string, string | number>;
  overridable: ConfigField[];
}

export interface ArchiveSummary {
  slug: string;
  item_count: number;
  image_count: number;
  audio_count: number;
  has_video: boolean;
  modified_at: string;
}

export interface ArchiveItem {
  title: string;
  description: string;
  image_prompts: string[];
  image_urls: string[];
  titled_image_urls: string[];
  audio_url: string | null;
}

export interface ArchiveDetail {
  slug: string;
  video_url: string | null;
  items: ArchiveItem[];
}
```

- [ ] **Step 8: Write `frontend/src/lib/api.ts`**

```ts
import type {
  ArchiveDetail,
  ArchiveSummary,
  ConfigPayload,
  CreateRunRequest,
  ItemPayload,
  RunDetail,
  RunSummary,
} from "./types";

/** An error the server reported, carrying its status so callers can branch. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    // FastAPI puts the message in `detail`; validation errors make it an array.
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((entry) => entry.msg ?? String(entry)).join(", ")
          : response.statusText || `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const getConfig = () => request<ConfigPayload>("/config");

export const listRuns = () => request<RunSummary[]>("/runs");

export const createRun = (payload: CreateRunRequest) =>
  request<RunDetail>("/runs", { method: "POST", body: JSON.stringify(payload) });

export const getRun = (runId: string) => request<RunDetail>(`/runs/${runId}`);

export const approveItems = (runId: string, items: ItemPayload[]) =>
  request<RunDetail>(`/runs/${runId}/items`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });

export const cancelRun = (runId: string) =>
  request<RunDetail>(`/runs/${runId}/cancel`, { method: "POST" });

export const listArchives = () => request<ArchiveSummary[]>("/archives");

export const getArchive = (slug: string) =>
  request<ArchiveDetail>(`/archives/${slug}`);
```

- [ ] **Step 9: Run the tests and the dev server**

Run: `cd frontend && npm test`
Expected: PASS (5 tests)

Run: `cd frontend && npm run build`
Expected: type-checks and builds with no errors.

Start the backend (`uvicorn api.app:app --port 8000` from the repo root) and `npm run dev` in `frontend/`, then open `http://localhost:5173`. Expected: the default Vite page renders. Confirm the proxy works: `curl -s localhost:5173/api/health` returns `{"status":"ok"}`.

- [ ] **Step 10: Commit**

```bash
git add frontend .gitignore
git commit -m "feat: scaffold the React frontend with a typed API client"
```

---

### Task 9: App shell, routing and the run-polling hook

**Files:**
- Create: `frontend/src/hooks/useRun.ts`, `frontend/src/hooks/useRun.test.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- Delete: `frontend/src/App.css` (the Vite template's demo styles)

**Interfaces:**
- Consumes: `getRun`, `TERMINAL_STATUSES`, `RunDetail` (Task 8).
- Produces: `useRun(runId: string | null, intervalMs?: number) -> { run: RunDetail | null; error: string | null; loading: boolean; refresh: () => void }` and the route table `/`, `/runs/:runId`, `/archives`, `/archives/:slug`, `/config`.

- [ ] **Step 1: Write the failing hook test**

Create `frontend/src/hooks/useRun.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRun } from "./useRun";

function mockSequence(bodies: unknown[]) {
  let index = 0;
  const fetchMock = vi.fn(async () => {
    const body = bodies[Math.min(index, bodies.length - 1)];
    index += 1;
    return { ok: true, status: 200, statusText: "", json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRun", () => {
  it("does nothing without a run id", () => {
    const fetchMock = mockSequence([{}]);
    const { result } = renderHook(() => useRun(null, 5));
    expect(result.current.run).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls until the run reaches a terminal status", async () => {
    const fetchMock = mockSequence([
      { id: "abc", status: "generating_media" },
      { id: "abc", status: "generating_media" },
      { id: "abc", status: "completed" },
    ]);

    const { result } = renderHook(() => useRun("abc", 5));
    await waitFor(() => expect(result.current.run?.status).toBe("completed"));

    const settled = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(fetchMock.mock.calls.length).toBe(settled);
  });

  it("keeps polling through a transient failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ id: "abc", status: "completed" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRun("abc", 5));
    await waitFor(() => expect(result.current.error).toBe("network down"));
    await waitFor(() => expect(result.current.run?.status).toBe("completed"));
    expect(result.current.error).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./useRun"`

- [ ] **Step 3: Write `frontend/src/hooks/useRun.ts`**

```ts
import { useCallback, useEffect, useState } from "react";

import { getRun } from "@/lib/api";
import { TERMINAL_STATUSES, type RunDetail } from "@/lib/types";

export interface UseRunResult {
  run: RunDetail | null;
  error: string | null;
  loading: boolean;
  /** Fetch immediately instead of waiting for the next poll. */
  refresh: () => void;
}

/**
 * Poll one run until it reaches a terminal status.
 *
 * A failed request does not stop the loop — the backend restarting mid-run
 * should not freeze the view — but the error is surfaced so the UI can say so.
 */
export function useRun(runId: string | null, intervalMs = 2000): UseRunResult {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(runId !== null);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setLoading(false);
      return;
    }

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const next = await getRun(runId);
        if (!active) return;
        setRun(next);
        setError(null);
        if (!TERMINAL_STATUSES.has(next.status)) {
          timer = setTimeout(tick, intervalMs);
        }
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : String(caught));
        timer = setTimeout(tick, intervalMs);
      } finally {
        if (active) setLoading(false);
      }
    };

    void tick();

    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId, intervalMs, nonce]);

  return { run, error, loading, refresh };
}
```

- [ ] **Step 4: Write the app shell**

Replace `frontend/src/App.tsx` with:

```tsx
import { NavLink, Route, Routes } from "react-router-dom";

import ArchiveDetailPage from "@/pages/ArchiveDetailPage";
import ArchivesPage from "@/pages/ArchivesPage";
import ConfigPage from "@/pages/ConfigPage";
import NewRunPage from "@/pages/NewRunPage";
import RunPage from "@/pages/RunPage";

const NAV = [
  { to: "/", label: "New run", end: true },
  { to: "/archives", label: "Archives", end: false },
  { to: "/config", label: "Config", end: false },
];

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b">
        <nav className="mx-auto flex max-w-4xl gap-4 px-6 py-4">
          <span className="font-semibold">Auto YouTube Generator</span>
          <div className="flex gap-4 text-sm">
            {NAV.map((entry) => (
              <NavLink
                key={entry.to}
                to={entry.to}
                end={entry.end}
                className={({ isActive }) =>
                  isActive ? "font-medium underline" : "text-muted-foreground"
                }
              >
                {entry.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <Routes>
          <Route path="/" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/archives" element={<ArchivesPage />} />
          <Route path="/archives/:slug" element={<ArchiveDetailPage />} />
          <Route path="/config" element={<ConfigPage />} />
        </Routes>
      </main>
    </div>
  );
}
```

Replace `frontend/src/main.tsx` with:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

Delete `frontend/src/App.css`.

- [ ] **Step 5: Add placeholder pages so the app compiles**

Create these five files. Each is replaced by a later task; they exist now only so `App.tsx` type-checks.

`frontend/src/pages/NewRunPage.tsx`, `RunPage.tsx`, `ArchivesPage.tsx`, `ArchiveDetailPage.tsx`, `ConfigPage.tsx` — each containing, with the matching name:

```tsx
export default function NewRunPage() {
  return <p>Not built yet.</p>;
}
```

- [ ] **Step 6: Run tests and the build**

Run: `cd frontend && npm test && npm run build`
Expected: PASS (8 tests total), build succeeds.

Start both servers and open `http://localhost:5173`. Expected: the nav bar renders and all three links route without a full page reload.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: add app routing and the run-polling hook"
```

---

### Task 10: New-run form

**Files:**
- Modify: `frontend/src/pages/NewRunPage.tsx`
- Test: `frontend/src/pages/NewRunPage.test.tsx`

**Interfaces:**
- Consumes: `createRun`, `getConfig`, `ApiError`, `ConfigField`, `useNavigate`.
- Produces: the route at `/`. Navigates to `/runs/:runId` on success.

**Behaviour:** topic (required) and item count (default 5, min 1) plus a "Let me review the items before generating media" checkbox. Overrides are optional: each overridable field renders with the current value as its placeholder, and only fields the user actually filled in are sent. A 409 shows the server's message and a link to the active run.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/NewRunPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import NewRunPage from "./NewRunPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => navigate };
});

const config = {
  values: { IMAGE_QUALITY: "medium", MAX_RETRIES: 5 },
  overridable: [
    {
      name: "IMAGE_QUALITY",
      type: "str",
      choices: ["low", "medium", "high"],
      description: "Higher costs more.",
    },
    { name: "MAX_RETRIES", type: "int", choices: null, description: "Attempts." },
  ],
};

function mockApi(createResponse: { status: number; body: unknown }) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return {
        ok: createResponse.status < 300,
        status: createResponse.status,
        statusText: "",
        json: async () => createResponse.body,
      };
    }
    return { ok: true, status: 200, statusText: "", json: async () => config };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  navigate.mockReset();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <NewRunPage />
    </MemoryRouter>,
  );
}

describe("NewRunPage", () => {
  it("creates a run and navigates to it", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Extinct animals");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/runs/abc"));

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      topic: "Extinct animals",
      num_items: 5,
      review_items: false,
      overrides: {},
    });
  });

  it("sends only the overrides that were filled in", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await screen.findByLabelText("MAX_RETRIES");
    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.type(screen.getByLabelText("MAX_RETRIES"), "9");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string).overrides).toEqual({
      MAX_RETRIES: "9",
    });
  });

  it("shows the server's message when a run is already active", async () => {
    mockApi({ status: 409, body: { detail: "run xyz is still generating_media" } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    expect(
      await screen.findByText(/run xyz is still generating_media/i),
    ).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("will not submit a blank topic", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /start run/i }));
    expect(await screen.findByText(/enter a topic/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      false,
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — the page renders "Not built yet." so `getByLabelText(/topic/i)` throws.

- [ ] **Step 3: Write `frontend/src/pages/NewRunPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRun, getConfig } from "@/lib/api";
import type { ConfigField } from "@/lib/types";

export default function NewRunPage() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [numItems, setNumItems] = useState(5);
  const [reviewItems, setReviewItems] = useState(false);
  const [fields, setFields] = useState<ConfigField[]>([]);
  const [current, setCurrent] = useState<Record<string, string | number>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getConfig()
      .then((payload) => {
        setFields(payload.overridable);
        setCurrent(payload.values);
      })
      .catch(() => {
        // The form still works without the override section.
        setFields([]);
      });
  }, []);

  const setOverride = (name: string, value: string) =>
    setOverrides((previous) => ({ ...previous, [name]: value }));

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!topic.trim()) {
      setError("Enter a topic first.");
      return;
    }

    // Blank fields mean "leave this alone", not "set it to empty".
    const filled = Object.fromEntries(
      Object.entries(overrides).filter(([, value]) => value.trim() !== ""),
    );

    setSubmitting(true);
    try {
      const run = await createRun({
        topic: topic.trim(),
        num_items: numItems,
        review_items: reviewItems,
        overrides: filled,
      });
      navigate(`/runs/${run.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>New run</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="topic">Topic</Label>
            <Input
              id="topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="Top 5 Extinct Animals"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="num-items">Number of items</Label>
            <Input
              id="num-items"
              type="number"
              min={1}
              max={50}
              value={numItems}
              onChange={(event) => setNumItems(Number(event.target.value))}
              className="w-32"
            />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="review"
              checked={reviewItems}
              onCheckedChange={(checked) => setReviewItems(checked === true)}
            />
            <Label htmlFor="review" className="font-normal">
              Let me review the items before generating media
            </Label>
          </div>
        </CardContent>
      </Card>

      {fields.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Overrides for this run (optional)
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {fields.map((field) => (
              <div key={field.name} className="space-y-1">
                <Label htmlFor={field.name}>{field.name}</Label>
                <Input
                  id={field.name}
                  value={overrides[field.name] ?? ""}
                  onChange={(event) => setOverride(field.name, event.target.value)}
                  placeholder={String(current[field.name] ?? "")}
                  list={field.choices ? `${field.name}-choices` : undefined}
                />
                {field.choices && (
                  <datalist id={`${field.name}-choices`}>
                    {field.choices.map((choice) => (
                      <option key={choice} value={choice} />
                    ))}
                  </datalist>
                )}
                <p className="text-xs text-muted-foreground">{field.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" disabled={submitting}>
        {submitting ? "Starting..." : "Start run"}
      </Button>
    </form>
  );
}
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/NewRunPage.tsx frontend/src/pages/NewRunPage.test.tsx
git commit -m "feat: add the new-run form"
```

---

### Task 11: Live run progress

Three presentational components plus the run page that polls and composes them.

**Files:**
- Create: `frontend/src/components/StageProgress.tsx`, `frontend/src/components/AssetList.tsx`, `frontend/src/components/LogPanel.tsx`, `frontend/src/components/StageProgress.test.tsx`
- Modify: `frontend/src/pages/RunPage.tsx`
- Test: `frontend/src/pages/RunPage.test.tsx`

**Interfaces:**
- Consumes: `useRun` (Task 9), `cancelRun` (Task 8), `STAGE_SEQUENCE`, `TERMINAL_STATUSES`, `RunDetail`, `AssetStatus`.
- Produces:
  - `<StageProgress run={run} />`
  - `<AssetList assets={assets} total={total} />`
  - `<LogPanel logs={logs} />`
  - `RunPage` at `/runs/:runId`. The `awaiting_review` branch is added in Task 12; here it just shows the status.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/StageProgress.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StageProgress from "./StageProgress";
import type { RunDetail } from "@/lib/types";

function makeRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "abc",
    topic: "Birds",
    num_items: 2,
    status: "generating_media",
    created_at: "2026-09-03T00:00:00Z",
    finished_at: null,
    review_items: false,
    overrides: {},
    items: [],
    assets: [],
    asset_total: 0,
    logs: [],
    error: null,
    video_url: null,
    archive_slug: null,
    ...overrides,
  };
}

describe("StageProgress", () => {
  it("marks stages before the current one as done", () => {
    render(<StageProgress run={makeRun()} />);
    expect(screen.getByTestId("stage-generating_list")).toHaveTextContent("done");
    expect(screen.getByTestId("stage-generating_media")).toHaveTextContent(
      "running",
    );
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("pending");
  });

  it("hides the review stage when review was not requested", () => {
    render(<StageProgress run={makeRun()} />);
    expect(screen.queryByTestId("stage-awaiting_review")).toBeNull();
  });

  it("shows the review stage when review was requested", () => {
    render(<StageProgress run={makeRun({ review_items: true })} />);
    expect(screen.getByTestId("stage-awaiting_review")).toBeInTheDocument();
  });

  it("marks every stage done when the run completed", () => {
    render(<StageProgress run={makeRun({ status: "completed" })} />);
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("done");
  });

  it("leaves unreached stages pending when the run failed", () => {
    render(
      <StageProgress
        run={makeRun({ status: "failed", error: "PipelineError: no images" })}
      />,
    );
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("pending");
  });
});
```

Create `frontend/src/pages/RunPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunPage from "./RunPage";

function mockRun(body: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    statusText: "",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/runs/abc"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const base = {
  id: "abc",
  topic: "Birds",
  num_items: 2,
  created_at: "2026-09-03T00:00:00Z",
  finished_at: null,
  review_items: false,
  overrides: {},
  items: [],
  assets: [],
  asset_total: 0,
  logs: [],
  error: null,
  video_url: null,
  archive_slug: null,
};

describe("RunPage", () => {
  it("shows the topic and the asset counter", async () => {
    mockRun({
      ...base,
      status: "generating_media",
      asset_total: 4,
      assets: [
        { label: "image item 1 prompt 1", ok: true, error: null },
        { label: "audio item 1", ok: false, error: "BadRequestError: nope" },
      ],
    });

    renderPage();

    expect(await screen.findByText("Birds")).toBeInTheDocument();
    expect(screen.getByText("2 of 4")).toBeInTheDocument();
    expect(screen.getByText(/BadRequestError: nope/)).toBeInTheDocument();
  });

  it("shows the error when the run failed", async () => {
    mockRun({ ...base, status: "failed", error: "PipelineError: no images" });
    renderPage();
    expect(await screen.findByText(/PipelineError: no images/)).toBeInTheDocument();
  });

  it("renders the video and an archive link when the run completed", async () => {
    mockRun({
      ...base,
      status: "completed",
      finished_at: "2026-09-03T00:10:00Z",
      video_url: "/media/outputs/video_output/final_video_short.mp4?run=abc",
      archive_slug: "birds",
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("run-video")).toHaveAttribute(
        "src",
        "/media/outputs/video_output/final_video_short.mp4?run=abc",
      ),
    );
    expect(screen.getByRole("link", { name: /open archive/i })).toHaveAttribute(
      "href",
      "/archives/birds",
    );
  });

  it("shows the log lines", async () => {
    mockRun({ ...base, status: "completed", logs: ["Generating 2 items...", "Done."] });
    renderPage();
    expect(await screen.findByText("Generating 2 items...")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./StageProgress"`, and RunPage renders "Not built yet."

- [ ] **Step 3: Write `frontend/src/components/StageProgress.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import { STAGE_SEQUENCE, TERMINAL_STATUSES, type RunDetail } from "@/lib/types";

type StageState = "done" | "running" | "pending";

/**
 * Which stages are behind, on, and ahead of the run's current status.
 *
 * A completed run has every stage behind it; a failed or cancelled run leaves
 * the stages it never reached as pending, which is the honest reading.
 */
function stateFor(run: RunDetail, index: number, currentIndex: number): StageState {
  if (run.status === "completed") return "done";
  if (currentIndex < 0) return "pending";
  if (index < currentIndex) return "done";
  if (index === currentIndex) {
    return TERMINAL_STATUSES.has(run.status) ? "done" : "running";
  }
  return "pending";
}

const VARIANT: Record<StageState, "default" | "secondary" | "outline"> = {
  done: "default",
  running: "secondary",
  pending: "outline",
};

export default function StageProgress({ run }: { run: RunDetail }) {
  const stages = STAGE_SEQUENCE.filter(
    (stage) => stage.status !== "awaiting_review" || run.review_items,
  );
  const currentIndex = stages.findIndex((stage) => stage.status === run.status);

  return (
    <ol className="flex flex-wrap gap-2">
      {stages.map((stage, index) => {
        const state = stateFor(run, index, currentIndex);
        return (
          <li key={stage.status} data-testid={`stage-${stage.status}`}>
            <Badge variant={VARIANT[state]}>
              {stage.label} <span className="ml-1 opacity-70">{state}</span>
            </Badge>
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/AssetList.tsx`**

```tsx
import { Progress } from "@/components/ui/progress";
import type { AssetStatus } from "@/lib/types";

/** Per-asset outcomes for the stage that is running now. */
export default function AssetList({
  assets,
  total,
}: {
  assets: AssetStatus[];
  total: number;
}) {
  if (total === 0 && assets.length === 0) return null;

  const percent = total > 0 ? Math.round((assets.length / total) * 100) : 0;
  const failed = assets.filter((asset) => !asset.ok);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Progress value={percent} className="w-64" />
        <span className="text-sm text-muted-foreground">
          {assets.length} of {total}
        </span>
      </div>

      {failed.length > 0 && (
        <ul className="space-y-1 text-sm text-destructive">
          {failed.map((asset) => (
            <li key={asset.label}>
              {asset.label}: {asset.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/LogPanel.tsx`**

```tsx
import { useEffect, useRef } from "react";

/** Pipeline output, pinned to the newest line. */
export default function LogPanel({ logs }: { logs: string[] }) {
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);

  if (logs.length === 0) return null;

  return (
    <pre className="max-h-64 overflow-auto rounded border bg-muted p-3 text-xs whitespace-pre-wrap">
      {logs.map((line, index) => (
        <div key={`${index}-${line}`}>{line}</div>
      ))}
      <div ref={bottom} />
    </pre>
  );
}
```

- [ ] **Step 6: Write `frontend/src/pages/RunPage.tsx`**

```tsx
import { Link, useParams } from "react-router-dom";

import AssetList from "@/components/AssetList";
import LogPanel from "@/components/LogPanel";
import StageProgress from "@/components/StageProgress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRun } from "@/hooks/useRun";
import { cancelRun } from "@/lib/api";
import { TERMINAL_STATUSES } from "@/lib/types";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, error, loading, refresh } = useRun(runId ?? null);

  if (loading && !run) return <p>Loading run...</p>;
  if (!run) return <Alert variant="destructive"><AlertDescription>{error ?? "Run not found."}</AlertDescription></Alert>;

  const finished = TERMINAL_STATUSES.has(run.status);

  const onCancel = async () => {
    try {
      await cancelRun(run.id);
    } finally {
      refresh();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">{run.topic}</h1>
          <p className="text-sm text-muted-foreground">
            {run.num_items} items · {run.status}
          </p>
        </div>
        {!finished && (
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>

      <StageProgress run={run} />

      {!finished && (
        <p className="text-xs text-muted-foreground">
          Cancelling stops the run at the next stage boundary. Work already in
          flight — an OpenAI batch or a video render — finishes first.
        </p>
      )}

      <AssetList assets={run.assets} total={run.asset_total} />

      {error && (
        <Alert>
          <AlertDescription>
            Lost contact with the server ({error}). Still retrying.
          </AlertDescription>
        </Alert>
      )}

      {run.error && (
        <Alert variant="destructive">
          <AlertDescription className="whitespace-pre-wrap">
            {run.error}
          </AlertDescription>
        </Alert>
      )}

      {run.video_url && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Finished video</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <video
              data-testid="run-video"
              src={run.video_url}
              controls
              className="max-h-[70vh] rounded border"
            />
            {run.archive_slug && (
              <Link
                to={`/archives/${run.archive_slug}`}
                className="text-sm underline"
              >
                Open archive
              </Link>
            )}
          </CardContent>
        </Card>
      )}

      <LogPanel logs={run.logs} />
    </div>
  );
}
```

- [ ] **Step 7: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS (21 tests total)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components frontend/src/pages/RunPage.tsx frontend/src/pages/RunPage.test.tsx
git commit -m "feat: show live run progress, assets and logs"
```

---

### Task 12: Item review and editing

When a run is `awaiting_review`, the run page swaps in an editor for the generated items. The user can change titles, descriptions and prompts, add or remove a prompt, and remove an item entirely; approving posts the edited list and the run resumes.

**Files:**
- Create: `frontend/src/components/ItemEditor.tsx`
- Modify: `frontend/src/pages/RunPage.tsx`
- Test: `frontend/src/components/ItemEditor.test.tsx`

**Interfaces:**
- Consumes: `approveItems` (Task 8), `ItemPayload`, the `RunPage` shell (Task 11).
- Produces: `<ItemEditor runId={string} items={ItemPayload[]} onApproved={() => void} />`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ItemEditor.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItemEditor from "./ItemEditor";

const items = [
  { title: "Dodo", description: "A bird.", image_prompts: ["a", "b"] },
  { title: "Moa", description: "A taller bird.", image_prompts: ["c"] },
];

function mockPost(status = 200, body: unknown = { id: "abc" }) {
  const fetchMock = vi.fn(async () => ({
    ok: status < 300,
    status,
    statusText: "",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("ItemEditor", () => {
  it("posts the edited items", async () => {
    const fetchMock = mockPost();
    const onApproved = vi.fn();
    render(<ItemEditor runId="abc" items={items} onApproved={onApproved} />);

    const title = screen.getByLabelText("Item 1 title");
    await userEvent.clear(title);
    await userEvent.type(title, "Great Auk");
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(onApproved).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].title).toBe("Great Auk");
    expect(body.items[1].title).toBe("Moa");
  });

  it("adds and removes image prompts", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    await userEvent.click(screen.getAllByRole("button", { name: /add prompt/i })[1]);
    await userEvent.type(screen.getByLabelText("Item 2 prompt 2"), "new prompt");
    await userEvent.click(
      screen.getByRole("button", { name: "Remove item 1 prompt 2" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].image_prompts).toEqual(["a"]);
    expect(body.items[1].image_prompts).toEqual(["c", "new prompt"]);
  });

  it("removes an item", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove item 1" }));
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items).toHaveLength(1);
    expect(body.items[0].title).toBe("Moa");
  });

  it("shows the server's rejection message", async () => {
    mockPost(400, { detail: "item 1 is missing a usable 'image_prompts' list" });
    const onApproved = vi.fn();
    render(<ItemEditor runId="abc" items={items} onApproved={onApproved} />);

    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    expect(await screen.findByText(/image_prompts/)).toBeInTheDocument();
    expect(onApproved).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./ItemEditor"`

- [ ] **Step 3: Write `frontend/src/components/ItemEditor.tsx`**

```tsx
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { approveItems } from "@/lib/api";
import type { ItemPayload } from "@/lib/types";

interface Props {
  runId: string;
  items: ItemPayload[];
  onApproved: () => void;
}

/**
 * Edit the generated items before any media is paid for.
 *
 * Prompt counts are free-form here: the backend validates with
 * `expected_prompts=None`, so adding or removing a prompt is allowed and the
 * media stage adapts to whatever count each item ends up with.
 */
export default function ItemEditor({ runId, items, onApproved }: Props) {
  const [draft, setDraft] = useState<ItemPayload[]>(() =>
    items.map((item) => ({ ...item, image_prompts: [...item.image_prompts] })),
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateItem = (index: number, patch: Partial<ItemPayload>) =>
    setDraft((previous) =>
      previous.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );

  const updatePrompt = (index: number, promptIndex: number, value: string) =>
    updateItem(index, {
      image_prompts: draft[index].image_prompts.map((prompt, position) =>
        position === promptIndex ? value : prompt,
      ),
    });

  const addPrompt = (index: number) =>
    updateItem(index, { image_prompts: [...draft[index].image_prompts, ""] });

  const removePrompt = (index: number, promptIndex: number) =>
    updateItem(index, {
      image_prompts: draft[index].image_prompts.filter(
        (_, position) => position !== promptIndex,
      ),
    });

  const removeItem = (index: number) =>
    setDraft((previous) => previous.filter((_, position) => position !== index));

  const onApprove = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await approveItems(runId, draft);
      onApproved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Edit anything you want before images and narration are generated.
        Approving starts the paid work.
      </p>

      {draft.map((item, index) => (
        <Card key={index}>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-base">Item {index + 1}</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Remove item ${index + 1}`}
              onClick={() => removeItem(index)}
            >
              Remove item
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor={`title-${index}`}>Item {index + 1} title</Label>
              <Input
                id={`title-${index}`}
                value={item.title}
                onChange={(event) =>
                  updateItem(index, { title: event.target.value })
                }
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor={`description-${index}`}>
                Item {index + 1} description
              </Label>
              <Textarea
                id={`description-${index}`}
                value={item.description}
                onChange={(event) =>
                  updateItem(index, { description: event.target.value })
                }
              />
            </div>

            <div className="space-y-2">
              {item.image_prompts.map((prompt, promptIndex) => (
                <div key={promptIndex} className="space-y-1">
                  <Label htmlFor={`prompt-${index}-${promptIndex}`}>
                    Item {index + 1} prompt {promptIndex + 1}
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id={`prompt-${index}-${promptIndex}`}
                      value={prompt}
                      onChange={(event) =>
                        updatePrompt(index, promptIndex, event.target.value)
                      }
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove item ${index + 1} prompt ${promptIndex + 1}`}
                      onClick={() => removePrompt(index, promptIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => addPrompt(index)}>
                Add prompt
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button onClick={onApprove} disabled={submitting || draft.length === 0}>
        {submitting ? "Approving..." : "Approve and generate media"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Wire the editor into `RunPage`**

In `frontend/src/pages/RunPage.tsx`, add the import:

```tsx
import ItemEditor from "@/components/ItemEditor";
```

and insert this block immediately after the `<StageProgress run={run} />` line:

```tsx
      {run.status === "awaiting_review" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Review the generated items</CardTitle>
          </CardHeader>
          <CardContent>
            <ItemEditor
              runId={run.id}
              items={run.items}
              onApproved={refresh}
            />
          </CardContent>
        </Card>
      )}
```

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test && npm run build`
Expected: PASS (25 tests total), build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ItemEditor.tsx frontend/src/components/ItemEditor.test.tsx frontend/src/pages/RunPage.tsx
git commit -m "feat: let items be reviewed and edited before media generation"
```

---

### Task 13: Archive browser

**Files:**
- Modify: `frontend/src/pages/ArchivesPage.tsx`, `frontend/src/pages/ArchiveDetailPage.tsx`
- Test: `frontend/src/pages/ArchivesPage.test.tsx`, `frontend/src/pages/ArchiveDetailPage.test.tsx`

**Interfaces:**
- Consumes: `listArchives`, `getArchive`, `ArchiveSummary`, `ArchiveDetail` (Task 8).
- Produces: the routes `/archives` and `/archives/:slug`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/ArchivesPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ArchivesPage from "./ArchivesPage";

function mockJson(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, statusText: "", json: async () => body })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ArchivesPage", () => {
  it("lists each archive with its counts and a link", async () => {
    mockJson([
      {
        slug: "top_5_extinct_animals",
        item_count: 5,
        image_count: 15,
        audio_count: 5,
        has_video: true,
        modified_at: "2026-08-18T10:00:00+00:00",
      },
    ]);

    render(
      <MemoryRouter>
        <ArchivesPage />
      </MemoryRouter>,
    );

    const link = await screen.findByRole("link", { name: /top_5_extinct_animals/ });
    expect(link).toHaveAttribute("href", "/archives/top_5_extinct_animals");
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  it("says so when there are no archives", async () => {
    mockJson([]);
    render(
      <MemoryRouter>
        <ArchivesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/no archives yet/i)).toBeInTheDocument();
  });
});
```

Create `frontend/src/pages/ArchiveDetailPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ArchiveDetailPage from "./ArchiveDetailPage";

function mockJson(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, status, statusText: "", json: async () => body })),
  );
}

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/archives/birds"]}>
      <Routes>
        <Route path="/archives/:slug" element={<ArchiveDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ArchiveDetailPage", () => {
  it("renders the video, images and audio", async () => {
    mockJson({
      slug: "birds",
      video_url: "/media/generated_data/birds/final_video_short.mp4",
      items: [
        {
          title: "Dodo",
          description: "A bird.",
          image_prompts: ["a"],
          image_urls: ["/media/generated_data/birds/images/item_01_prompt_01.png"],
          titled_image_urls: [],
          audio_url: "/media/generated_data/birds/audio/item_01.mp3",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Dodo")).toBeInTheDocument();
    expect(screen.getByTestId("archive-video")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/final_video_short.mp4",
    );
    expect(screen.getByAltText("Dodo image 1")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/images/item_01_prompt_01.png",
    );
    expect(screen.getByTestId("audio-1")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/audio/item_01.mp3",
    );
  });

  it("copes with an archive that has no video", async () => {
    mockJson({ slug: "old", video_url: null, items: [] });
    renderPage();
    expect(await screen.findByText(/no video/i)).toBeInTheDocument();
  });

  it("shows the error for a missing archive", async () => {
    mockJson({ detail: "no archive birds" }, false, 404);
    renderPage();
    expect(await screen.findByText(/no archive birds/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — both pages render "Not built yet."

- [ ] **Step 3: Write `frontend/src/pages/ArchivesPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listArchives } from "@/lib/api";
import type { ArchiveSummary } from "@/lib/types";

export default function ArchivesPage() {
  const [archives, setArchives] = useState<ArchiveSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listArchives()
      .then(setArchives)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, []);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (archives === null) return <p>Loading archives...</p>;
  if (archives.length === 0) return <p>No archives yet. Start a run first.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Topic</TableHead>
          <TableHead>Items</TableHead>
          <TableHead>Images</TableHead>
          <TableHead>Audio</TableHead>
          <TableHead>Video</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {archives.map((archive) => (
          <TableRow key={archive.slug}>
            <TableCell>
              <Link to={`/archives/${archive.slug}`} className="underline">
                {archive.slug}
              </Link>
            </TableCell>
            <TableCell>{archive.item_count}</TableCell>
            <TableCell>{archive.image_count}</TableCell>
            <TableCell>{archive.audio_count}</TableCell>
            <TableCell>{archive.has_video ? "yes" : "no"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: Write `frontend/src/pages/ArchiveDetailPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getArchive } from "@/lib/api";
import type { ArchiveDetail } from "@/lib/types";

export default function ArchiveDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [archive, setArchive] = useState<ArchiveDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    getArchive(slug)
      .then(setArchive)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, [slug]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!archive) return <p>Loading archive...</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{archive.slug}</h1>

      {archive.video_url ? (
        <video
          data-testid="archive-video"
          src={archive.video_url}
          controls
          className="max-h-[70vh] rounded border"
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          No video was archived for this run.
        </p>
      )}

      <Separator />

      {archive.items.map((item, index) => (
        <Card key={`${item.title}-${index}`}>
          <CardHeader>
            <CardTitle className="text-base">{item.title}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">{item.description}</p>

            {item.audio_url && (
              <audio
                data-testid={`audio-${index + 1}`}
                src={item.audio_url}
                controls
                className="w-full"
              />
            )}

            <div className="flex flex-wrap gap-2">
              {item.image_urls.map((url, imageIndex) => (
                <img
                  key={url}
                  src={url}
                  alt={`${item.title} image ${imageIndex + 1}`}
                  className="h-32 w-32 rounded border object-cover"
                />
              ))}
              {item.titled_image_urls.map((url, imageIndex) => (
                <img
                  key={url}
                  src={url}
                  alt={`${item.title} titled image ${imageIndex + 1}`}
                  className="h-32 w-auto rounded border object-contain"
                />
              ))}
            </div>

            <ul className="list-disc pl-5 text-xs text-muted-foreground">
              {item.image_prompts.map((prompt, promptIndex) => (
                <li key={promptIndex}>{prompt}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS (30 tests total)

- [ ] **Step 6: Check it against the real archives**

With both servers running, open `http://localhost:5173/archives`. Expected: the four real archives listed; clicking one shows its items with images and playable audio. `top_5_extinct_animals` has no video — confirm the "No video was archived" line appears rather than a broken player.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ArchivesPage.tsx frontend/src/pages/ArchiveDetailPage.tsx frontend/src/pages/ArchivesPage.test.tsx frontend/src/pages/ArchiveDetailPage.test.tsx
git commit -m "feat: browse archived runs"
```

---

### Task 14: Config viewer

Read-only table of every constant currently in force, with the overridable ones marked so it is obvious which can be changed per run.

**Files:**
- Modify: `frontend/src/pages/ConfigPage.tsx`
- Test: `frontend/src/pages/ConfigPage.test.tsx`

**Interfaces:**
- Consumes: `getConfig`, `ConfigPayload` (Task 8).
- Produces: the route `/config`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ConfigPage.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConfigPage from "./ConfigPage";

function mockConfig() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({
        values: { IMAGE_QUALITY: "medium", VIDEO_WIDTH: 1080 },
        overridable: [
          {
            name: "IMAGE_QUALITY",
            type: "str",
            choices: ["low", "medium", "high"],
            description: "Higher costs more.",
          },
        ],
      }),
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ConfigPage", () => {
  it("shows every value and marks the overridable ones", async () => {
    mockConfig();
    render(<ConfigPage />);

    const overridable = await screen.findByTestId("row-IMAGE_QUALITY");
    expect(within(overridable).getByText("medium")).toBeInTheDocument();
    expect(within(overridable).getByText(/per run/i)).toBeInTheDocument();

    const fixed = screen.getByTestId("row-VIDEO_WIDTH");
    expect(within(fixed).getByText("1080")).toBeInTheDocument();
    expect(within(fixed).queryByText(/per run/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — the page renders "Not built yet."

- [ ] **Step 3: Write `frontend/src/pages/ConfigPage.tsx`**

```tsx
import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getConfig } from "@/lib/api";
import type { ConfigPayload } from "@/lib/types";

export default function ConfigPage() {
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, []);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!config) return <p>Loading config...</p>;

  const overridable = new Map(
    config.overridable.map((field) => [field.name, field]),
  );
  const names = Object.keys(config.values).sort();

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Defaults live in <code>config.py</code> and can be changed permanently
        with an environment variable of the same name. Fields marked{" "}
        <em>per run</em> can also be overridden for a single run from the new-run
        form.
      </p>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Notes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {names.map((name) => {
            const field = overridable.get(name);
            return (
              <TableRow key={name} data-testid={`row-${name}`}>
                <TableCell className="font-mono text-xs">{name}</TableCell>
                <TableCell className="font-mono text-xs">
                  {String(config.values[name])}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {field && <Badge variant="secondary">per run</Badge>}{" "}
                  {field?.description}
                  {field?.choices && ` One of: ${field.choices.join(", ")}.`}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests and the build**

Run: `cd frontend && npm test && npm run build`
Expected: PASS (31 tests total), build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ConfigPage.tsx frontend/src/pages/ConfigPage.test.tsx
git commit -m "feat: show the effective pipeline config"
```

---

### Task 15: End-to-end verification and documentation

The only step in this plan that spends money. Do it once, on a cheap configuration.

**Files:**
- Modify: `README.md`
- Create: `frontend/README.md` — delete the Vite template's version and replace it.

**Interfaces:**
- Consumes: everything.
- Produces: no code.

- [ ] **Step 1: Run the whole backend suite**

Run: `pytest -v`
Expected: PASS, including the `slow` end-to-end render.

- [ ] **Step 2: Run the whole frontend suite and build**

Run: `cd frontend && npm test && npm run build`
Expected: PASS, build succeeds with no TypeScript errors.

- [ ] **Step 3: Drive one real run through the UI**

Start `uvicorn api.app:app --port 8000` from the repo root and `npm run dev` in `frontend/`. In the browser at `http://localhost:5173`:

1. Enter topic `Top 3 Deep Sea Creatures`, 3 items, tick **review**, and set the override `IMAGE_QUALITY` to `low` and `IMAGE_PROMPTS_PER_ITEM` to `1` to keep the cost down.
2. Confirm the run pauses at **Review items** with three editable items.
3. Edit one title, delete one item, then approve.
4. Confirm the asset counter advances (4 assets: 2 images + 2 narrations after the deletion), the stages tick over, and the finished video plays inline.
5. Follow **Open archive** and confirm `generated_data/top_3_deep_sea_creatures/` shows the two items, their images, titled images, audio and video.
6. Go back to **New run** and start a second run; confirm it succeeds now that the first is terminal.

Expected: every step behaves as described. If anything is wrong, fix it before continuing — this is the acceptance test for the whole plan.

- [ ] **Step 4: Confirm the CLI is unregressed**

Run: `python main.py --topic "Top 2 Fast Birds" --items 2`
Expected: the same `[1/5]` … `[5/5]` banners as before the refactor, and a video in `outputs/video_output/`.

- [ ] **Step 5: Update `README.md`**

Add this section immediately after the existing "How to Run the App → Run the Pipeline" block:

```markdown
### Run the Web UI

The web UI is two processes: the FastAPI backend and the Vite dev server.

**Terminal 1 — backend (must be started from the repository root):**

```bash
uvicorn api.app:app --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install   # first time only
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` and `/media` to the
backend, so there is nothing else to configure.

The UI can:

- start a run and watch it stage by stage, with per-asset success and failure
- pause after the item list is generated so you can edit titles, descriptions
  and image prompts before any images or narration are paid for
- override any of the tunables listed under [Configuration](#configuration) for
  a single run, without editing `.env`
- browse every archived run in `generated_data/` with its images, narration and
  video

**Only one run can be active at a time.** `outputs/` is a single shared
workspace with fixed filenames, so starting a second run while one is in flight
returns a conflict. Cancelling stops the run at the next stage boundary; work
already in flight finishes first.

Run history lives in memory. Restarting the backend clears it —
`generated_data/` is the durable record.

To serve the UI from the backend alone (no Vite process), build it first; the
backend serves `frontend/dist/` at `/` when that directory exists:

```bash
cd frontend && npm run build
```
```

Also add to the Development section, after the `pytest` instructions:

```markdown
Frontend tests:

```bash
cd frontend
npm test
```
```

- [ ] **Step 6: Replace `frontend/README.md`**

```markdown
# Frontend

React + TypeScript + Vite + Tailwind v4 + shadcn/ui.

Styling is deliberately plain — default shadcn components, no theme work yet.

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api and /media to :8000
npm test        # vitest
npm run build   # type-check and build into dist/
```

The backend must be running on port 8000 (`uvicorn api.app:app --port 8000`
from the repository root).

`src/lib/types.ts` mirrors `api/schemas.py` field for field. When you change
one, change the other.
```

- [ ] **Step 7: Commit**

```bash
git add README.md frontend/README.md
git commit -m "docs: document the web UI and how to run it"
```

---

## Notes for the executor

**Things that will bite you if you skip them:**

- Start `uvicorn` **from the repository root**, never from `api/`. Every path is CWD-relative.
- `pytest` uses `pythonpath = .` from `pytest.ini`, so `import api.app` works with no install step. Do not add a `setup.py` or `pyproject.toml`.
- The `outputs/` directory in this repo already holds assets from a previous run. Backend tests `monkeypatch.chdir(tmp_path)` precisely so they never touch it — keep doing that in every new test.
- `create_app()` is a factory rather than a module-level singleton because `StaticFiles(directory=...)` resolves its path at construction time. Tests must `chdir` **before** calling it.
- The four archives already in `generated_data/` predate `titled_images/` and the archived video. Any archive code that assumes those exist will crash on real data.
- shadcn's `init` rewrites `src/index.css`. Run it **after** setting up Tailwind, not before, and do not hand-edit the theme variables it writes — styling is out of scope.
