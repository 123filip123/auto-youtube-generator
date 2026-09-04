"""Render a Shorts frame for every generated shot."""

from concurrent.futures import ThreadPoolExecutor

import config
from models import Script
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import composed_image_path, section_image_path

from .utils import compose_frame


def compose_jobs(script: Script) -> list[Job]:
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        for shot_number in range(1, len(section.prompts) + 1):
            source = section_image_path(section_number, shot_number)
            destination = composed_image_path(section_number, shot_number)
            jobs.append(
                (
                    f"compose section {section_number} shot {shot_number}",
                    lambda s=source, d=destination: compose_frame(s, d),
                )
            )
    return jobs


def compose_frames_for_script(script: Script, *, on_done=None) -> list[TaskResult]:
    """Render every frame. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, compose_jobs(script), on_done=on_done)
