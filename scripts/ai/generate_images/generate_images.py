"""Fan a script's sections out into per-section chained image jobs.

Shots within a section are drawn as a chain: shot 2..N of a section continues
the shot before it, so they cannot run until it exists. That chaining resets
at every section boundary — a new section always starts fresh from its own
first shot, drawn from text alone, rather than continuing the previous
section's last frame. Sections are otherwise independent of each other, so
each section's chain runs as one job and different sections' jobs run in
parallel.
"""

from pathlib import Path
from typing import Callable, Sequence

from models import Script, Section
from utils.openai_support import Job, TaskResult
from utils.paths import section_image_path

from .utils import generate_image, generate_image_from_reference, styled_prompt


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
