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
from scripts.ai.generate_images.generate_images import anchor_jobs, followup_jobs
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
        for beat_number in range(1, len(item.image_prompts) + 1):
            candidate = image_path(item_number, beat_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def missing_titled_images(items: Sequence[Item]) -> list[Path]:
    """Every expected titled image that is absent or empty."""
    missing: list[Path] = []
    for item_number, item in enumerate(items, start=1):
        for beat_number in range(1, len(item.image_prompts) + 1):
            candidate = titled_image_path(item_number, beat_number)
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
    # One shared pool across both waves, so every stage stays under one cap.
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        # Wave one: every item's anchor frame, plus all the narration. Audio
        # rides along here rather than idling while the anchors are drawn.
        results = run_all(
            executor,
            anchor_jobs(items, client=client) + audio_jobs(items, client=client),
            on_done=on_asset,
        )
        # Wave two: the follow-up frames, each continuing an anchor that now
        # exists on disk. Built after wave one so a failed anchor is visible.
        results += run_all(
            executor, followup_jobs(items, client=client), on_done=on_asset
        )

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
