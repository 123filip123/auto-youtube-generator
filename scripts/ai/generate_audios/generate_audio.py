"""Fan section narration out into independent, parallelizable jobs."""

from models import Script
from utils.openai_support import Job
from utils.paths import section_audio_path

from .utils import generate_audio_for_section


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
