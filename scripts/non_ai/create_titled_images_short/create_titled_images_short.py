"""Render a titled Shorts frame for every generated image."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.media import available_prompt_numbers
from utils.paths import image_path, titled_image_path

from .utils import create_placeholder_titled_image, create_titled_image_short


def titled_image_jobs(items: Sequence[Item]) -> list[Job]:
    """One job per generated image, or a placeholder job for an item with none."""
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        prompt_numbers = available_prompt_numbers(
            item_number, len(item.image_prompts)
        )
        if not prompt_numbers:
            destination = titled_image_path(item_number, 1)
            jobs.append(
                (
                    f"placeholder image item {item_number}",
                    lambda t=item.title, d=destination: (
                        create_placeholder_titled_image(t, d)
                    ),
                )
            )
            continue
        for prompt_number in prompt_numbers:
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
    *,
    on_done=None,
) -> list[TaskResult]:
    """Render every titled image. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, titled_image_jobs(items), on_done=on_done)
