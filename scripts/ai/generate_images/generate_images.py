"""Fan an item's story beats out into anchor and follow-up image jobs.

Frames 2..N of an item are drawn as continuations of frame 1, so they cannot
run until it exists. Splitting them into two waves keeps every job independent
within its wave — the alternative, one sequential job per item, would cut
parallelism to the item count and coarsen the progress display.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path

from .utils import generate_image, generate_image_from_reference, styled_prompt


def anchor_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """One job per item: its first frame, drawn from the prompt alone."""
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        if not item.beats:
            continue
        prompt = styled_prompt(item.style, item.beats[0].prompt)
        destination = image_path(item_number, 1)
        jobs.append(
            (
                f"image item {item_number} beat 1",
                lambda p=prompt, d=destination: generate_image(p, d, client=client),
            )
        )
    return jobs


def followup_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """One job per later beat, each continuing its own item's anchor frame.

    Build these only after the anchor wave has run. A job whose anchor is
    missing raises `FileNotFoundError`, so a failed anchor is reported against
    every frame it blocked instead of silently producing nothing.
    """
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        reference = image_path(item_number, 1)
        for beat_number, beat in enumerate(item.beats[1:], start=2):
            prompt = styled_prompt(item.style, beat.prompt)
            destination = image_path(item_number, beat_number)
            jobs.append(
                (
                    f"image item {item_number} beat {beat_number}",
                    lambda p=prompt, r=reference, d=destination: (
                        generate_image_from_reference(p, r, d, client=client)
                    ),
                )
            )
    return jobs


def generate_images(items: Sequence[Item], *, client=None) -> list[TaskResult]:
    """Run both waves in order. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        anchors = run_all(executor, anchor_jobs(items, client=client))
        followups = run_all(executor, followup_jobs(items, client=client))
    return anchors + followups
