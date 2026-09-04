"""Fan item narration out into independent, parallelizable jobs."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item, Script
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import audio_path, section_audio_path

from .utils import generate_audio_for_item, generate_audio_for_section


def audio_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """Build one labelled, not-yet-run narration job per item."""
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        destination = audio_path(item_number)
        jobs.append(
            (
                f"audio item {item_number}",
                lambda i=item, d=destination: generate_audio_for_item(
                    i, d, client=client
                ),
            )
        )
    return jobs


def generate_audio_for_items(
    items: Sequence[Item], *, client=None
) -> list[TaskResult]:
    """Narrate every item in parallel. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, audio_jobs(items, client=client))


def section_audio_jobs(script: Script, *, client=None) -> list[Job]:
    """One narration job per section. All independent, all parallelizable."""
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        destination = section_audio_path(section_number)
        jobs.append(
            (
                f"audio section {section_number}",
                lambda s=section, d=destination: generate_audio_for_section(
                    s, d, client=client
                ),
            )
        )
    return jobs
