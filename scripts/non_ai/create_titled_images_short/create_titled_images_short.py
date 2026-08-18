"""Render a titled Shorts frame for every generated image."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path, titled_image_path

from .utils import create_titled_image_short


def titled_image_jobs(items: Sequence[Item]) -> list[Job]:
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number in range(1, len(item.image_prompts) + 1):
            source = image_path(item_number, prompt_number)
            destination = titled_image_path(item_number, prompt_number)
            label = f"titled image item {item_number} prompt {prompt_number}"
            jobs.append(
                (
                    label,
                    lambda s=source, t=item.title, d=destination: (
                        create_titled_image_short(s, t, d)
                    ),
                )
            )
    return jobs


def create_titled_images_for_items_short(
    items: Sequence[Item],
) -> list[TaskResult]:
    """Render every titled image. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, titled_image_jobs(items))
