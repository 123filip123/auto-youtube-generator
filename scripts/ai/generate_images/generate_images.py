"""Fan every item's image prompts out into independent, parallelizable jobs."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path

from .utils import generate_image


def image_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """Build one labelled, not-yet-run job per (item, prompt) pair.

    Returning callables rather than running them lets the pipeline merge these
    with the audio jobs into a single concurrency-capped pool.
    """
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number, prompt in enumerate(item.image_prompts, start=1):
            destination = image_path(item_number, prompt_number)
            label = f"image item {item_number} prompt {prompt_number}"
            jobs.append(
                (
                    label,
                    lambda p=prompt, d=destination: generate_image(p, d, client=client),
                )
            )
    return jobs


def generate_images(items: Sequence[Item], *, client=None) -> list[TaskResult]:
    """Generate every image in parallel. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, image_jobs(items, client=client))
