"""Stage orchestration for the video generation pipeline."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

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
from utils.openai_support import describe_failures, run_all
from utils.paths import (
    audio_path,
    ensure_output_dirs,
    image_path,
    list_items_path,
    titled_image_path,
)


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


def run_pipeline(topic: str, num_items: int, *, client=None) -> Path:
    """Run every stage end to end and return the path to the finished video."""
    ensure_output_dirs()

    print(f"\n[1/5] Generating {num_items} items for '{topic}'...")
    items = generate_list(topic, num_items, client=client)
    save_items(items, list_items_path())
    for number, item in enumerate(items, start=1):
        print(f"  {number}. {item.title}")

    total_jobs = len(items) + sum(len(item.image_prompts) for item in items)
    print(
        f"\n[2/5] Generating {total_jobs} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    # One shared pool, so image and audio work interleaves under a single cap.
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        jobs = image_jobs(items, client=client) + audio_jobs(items, client=client)
        results = run_all(executor, jobs)

    failures = describe_failures(results)
    if failures:
        print(f"\n{failures}")

    missing = missing_media(items)
    if missing:
        _fail("Media generation", missing)

    print("\n[3/5] Rendering titled images...")
    titled_results = create_titled_images_for_items_short(items)
    titled_failures = describe_failures(titled_results)
    if titled_failures:
        print(f"\n{titled_failures}")

    missing = missing_titled_images(items)
    if missing:
        _fail("Titled image rendering", missing)

    print("\n[4/5] Assembling video...")
    video = generate_video_short(items)

    print("\n[5/5] Archiving...")
    save_to_generated_data(topic, items)

    return video
