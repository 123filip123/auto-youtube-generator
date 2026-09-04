"""Stage orchestration for the video generation pipeline.

Each stage is callable on its own so a caller can stop between stages — the
web UI pauses after the prompt stage to let a human edit the script and its
drawings before any paid media is generated. `run_pipeline` composes all six
and is what the CLI uses.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import config
from models import Script, save_script
from scripts.ai.generate_audios.generate_audio import section_audio_jobs
from scripts.ai.generate_images.generate_images import (
    flatten_chain_results,
    section_chain_jobs,
)
from scripts.ai.generate_prompts.generate_prompts import generate_prompts
from scripts.ai.generate_script.generate_script import generate_script
from scripts.non_ai.compose_frames.compose_frames import compose_frames_for_script
from scripts.non_ai.generate_video_short.generate_video_short import (
    generate_video_from_script,
)
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_script_to_generated_data,
)
from utils.openai_support import TaskResult, describe_failures, run_all
from utils.paths import (
    composed_image_path,
    ensure_output_dirs,
    script_path,
    section_audio_path,
    section_image_path,
)

TOTAL_STAGES = 6

Log = Callable[[str], None]
AssetCallback = Callable[[TaskResult], None]


class PipelineError(RuntimeError):
    """A stage produced incomplete output, so the pipeline cannot continue."""


def _unusable(path: Path) -> bool:
    """A file is unusable if it is absent or empty."""
    return not path.exists() or path.stat().st_size == 0


def missing_media(script: Script) -> list[Path]:
    """Every expected narration and shot image that is absent or empty."""
    missing: list[Path] = []
    for section_number, section in enumerate(script.sections, start=1):
        candidate = section_audio_path(section_number)
        if _unusable(candidate):
            missing.append(candidate)
        for shot_number in range(1, len(section.prompts) + 1):
            candidate = section_image_path(section_number, shot_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def missing_composed_frames(script: Script) -> list[Path]:
    """Every expected composed frame that is absent or empty."""
    missing: list[Path] = []
    for section_number, section in enumerate(script.sections, start=1):
        for shot_number in range(1, len(section.prompts) + 1):
            candidate = composed_image_path(section_number, shot_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def _fail(stage: str, paths: list[Path]) -> None:
    listing = "\n".join(f"  - {path}" for path in paths)
    raise PipelineError(
        f"{stage} did not produce {len(paths)} required file(s):\n{listing}\n"
        f"Fix the underlying errors above and re-run."
    )


def media_job_total(script: Script) -> int:
    """One narration per section plus one image per shot."""
    return len(script.sections) + sum(
        len(section.prompts) for section in script.sections
    )


def compose_job_total(script: Script) -> int:
    """One composed frame per generated shot."""
    return sum(len(section.prompts) for section in script.sections)


def sections_without_shots(script: Script) -> list[str]:
    """Labels of sections carrying narration but no drawings.

    The AI never produces these — call 2 guarantees at least one prompt per
    section — but the review gate lets a human delete every drawing from a
    section, and nothing downstream notices: the chain jobs skip a promptless
    section, `missing_media` iterates an empty range so it flags nothing, and
    assembly then dies inside `segment_bounds` with a bare "Need at least one
    image per section, got 0" that names neither the section nor the cause.
    Catching it here fails before a cent is spent on narration.
    """
    return [
        f"{position}. {section.label}"
        for position, section in enumerate(script.sections, start=1)
        if not section.prompts
    ]


def _asset_reporter(on_asset: AssetCallback | None) -> AssetCallback | None:
    """Wrap a progress callback so chain jobs are not double-counted.

    A section chain reports each shot through its own `on_shot` as the shot
    lands. The wrapper result `run_all` produces when that job finishes
    carries the same shots again, so it is dropped — unless the job failed
    outright, in which case it is the only report there will be.
    """
    if on_asset is None:
        return None

    def report(result: TaskResult) -> None:
        if result.ok and isinstance(result.value, list):
            return
        on_asset(result)

    return report


def generate_script_stage(
    topic: str,
    target_seconds: int | None = None,
    *,
    client=None,
    log: Log = print,
) -> Script:
    """Stage 1: write the script and save it to disk."""
    ensure_output_dirs()
    target = config.TARGET_VIDEO_SECONDS if target_seconds is None else target_seconds
    log(f"Writing a {target}-second script for '{topic}'...")
    script = generate_script(topic, target, client=client)
    save_script(script, script_path())
    for section in script.sections:
        log(f"  {section.label}: {section.narration}")
    return script


def generate_prompts_stage(
    script: Script, *, client=None, log: Log = print
) -> Script:
    """Stage 2: design the style sheet and every drawing, then save."""
    log("Designing the drawings...")
    filled = generate_prompts(script, client=client)
    save_script(filled, script_path())
    total = compose_job_total(filled)
    log(f"  {total} drawing(s) across {len(filled.sections)} section(s).")
    return filled


def generate_media_stage(
    script: Script,
    *,
    client=None,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 3: narrate every section and draw every shot, then verify.

    Audio jobs and section chains go into one pool together. There are no
    waves any more: chaining is sequential inside a chain job, so ordering is
    that job's problem rather than the scheduler's.
    """
    ensure_output_dirs()

    empty = sections_without_shots(script)
    if empty:
        listing = "\n".join(f"  - {label}" for label in empty)
        raise PipelineError(
            f"{len(empty)} section(s) have narration but no drawings:\n{listing}\n"
            f"Add at least one drawing to each, or remove the section."
        )

    total = media_job_total(script)
    log(
        f"Generating {total} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        results = run_all(
            executor,
            section_chain_jobs(script, client=client, on_shot=on_asset)
            + section_audio_jobs(script, client=client),
            on_done=_asset_reporter(on_asset),
        )

    failures = describe_failures(flatten_chain_results(results))
    if failures:
        log(failures)

    missing = missing_media(script)
    if missing:
        _fail("Media generation", missing)


def compose_stage(
    script: Script,
    *,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 4: compose each shot onto its blurred backdrop."""
    log("Composing frames...")
    results = compose_frames_for_script(script, on_done=on_asset)

    failures = describe_failures(results)
    if failures:
        log(failures)

    missing = missing_composed_frames(script)
    if missing:
        _fail("Frame composition", missing)


def render_video_stage(
    script: Script, *, log: Log = print
) -> tuple[Path, list[float]]:
    """Stage 5: assemble the frames and narration into the final video."""
    log("Assembling video...")
    return generate_video_from_script(script)


def archive_stage(
    script: Script, durations: list[float], *, log: Log = print
) -> Path:
    """Stage 6: copy the whole run into `generated_data/<topic-slug>/`."""
    log("Archiving...")
    return save_script_to_generated_data(script, durations)


def _banner(step: int) -> Log:
    """A logger that stamps a `[n/6]` banner onto the stage's first line only."""
    pending = [True]

    def log(message: str) -> None:
        if pending[0]:
            pending[0] = False
            print(f"\n[{step}/{TOTAL_STAGES}] {message}")
        else:
            print(message)

    return log


def run_pipeline(
    topic: str, target_seconds: int | None = None, *, client=None
) -> Path:
    """Run every stage end to end and return the path to the finished video."""
    ensure_output_dirs()

    script = generate_script_stage(
        topic, target_seconds, client=client, log=_banner(1)
    )
    script = generate_prompts_stage(script, client=client, log=_banner(2))
    generate_media_stage(script, client=client, log=_banner(3))
    compose_stage(script, log=_banner(4))
    video, durations = render_video_stage(script, log=_banner(5))
    archive_stage(script, durations, log=_banner(6))

    return video
