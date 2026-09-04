"""Fan an item's story beats out into anchor and follow-up image jobs.

Frames 2..N of an item are drawn as continuations of frame 1, so they cannot
run until it exists. Splitting them into two waves keeps every job independent
within its wave — the alternative, one sequential job per item, would cut
parallelism to the item count and coarsen the progress display.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Sequence

import config
from models import Item, Script, Section
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path, section_image_path

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


def run_section_chain(
    section_number: int,
    section: Section,
    style: str,
    *,
    client=None,
    on_shot: Callable[[TaskResult], None] | None = None,
) -> list[TaskResult]:
    """Draw one section's shots in order, each continuing the one before.

    `reference` holds the last shot that actually succeeded, so a failure in
    the middle costs one frame and one continuity beat rather than every
    remaining shot in the section. Before anything has succeeded — including
    after a failed first shot — the next shot is drawn from text alone.

    Returns one `TaskResult` per shot. The caller flattens these with
    `flatten_chain_results`; `on_shot` fires as each one lands so a progress
    display still ticks per image rather than per section.
    """
    results: list[TaskResult] = []
    reference: Path | None = None

    for shot_number, prompt in enumerate(section.prompts, start=1):
        destination = section_image_path(section_number, shot_number)
        label = f"image section {section_number} shot {shot_number}"
        styled = styled_prompt(style, prompt)
        try:
            if reference is None:
                generate_image(styled, destination, client=client)
            else:
                generate_image_from_reference(
                    styled, reference, destination, client=client
                )
            result = TaskResult(label, value=destination)
            reference = destination
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            result = TaskResult(label, error=exc)

        results.append(result)
        if on_shot is not None:
            on_shot(result)

    return results


def section_chain_jobs(
    script: Script,
    *,
    client=None,
    on_shot: Callable[[TaskResult], None] | None = None,
) -> list[Job]:
    """One job per section. Sections are independent, so these run in parallel.

    Parallelism is bounded by section count rather than image count; wall time
    is roughly the longest single chain.
    """
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        if not section.prompts:
            continue
        jobs.append(
            (
                f"images section {section_number}",
                lambda n=section_number, s=section: run_section_chain(
                    n, s, script.style, client=client, on_shot=on_shot
                ),
            )
        )
    return jobs


def flatten_chain_results(results: Sequence[TaskResult]) -> list[TaskResult]:
    """Unwrap per-section result lists into one result per shot.

    A chain job that failed outright — rather than returning per-shot results —
    is kept as-is so the failure is still reported.
    """
    flat: list[TaskResult] = []
    for result in results:
        if result.ok and isinstance(result.value, list):
            flat.extend(result.value)
        else:
            flat.append(result)
    return flat
