"""Concatenate per-section clips into the final vertical video."""

import os
from pathlib import Path

from moviepy.editor import concatenate_videoclips

import config
from models import Script
from utils.paths import VIDEO_OUTPUT_DIR, video_output_path

from .utils import build_section_clip


def generate_video_from_script(script: Script) -> tuple[Path, list[float]]:
    """Render the script into one 1080x1920 video.

    Returns the output path and the measured duration of each section, so the
    archive can write real timings into `script.json` without reopening every
    mp3.
    """
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = video_output_path()

    last = len(script.sections)
    clips = [
        build_section_clip(
            section_number,
            section,
            is_first=section_number == 1,
            is_last=section_number == last,
        )
        for section_number, section in enumerate(script.sections, start=1)
    ]
    durations = [clip.duration for clip in clips]

    final_clip = concatenate_videoclips(clips)
    try:
        final_clip.write_videofile(
            str(output_path),
            fps=config.VIDEO_FPS,
            codec=config.VIDEO_CODEC,
            audio_codec=config.VIDEO_AUDIO_CODEC,
            preset=config.VIDEO_PRESET,
            threads=os.cpu_count() or 4,
        )
    finally:
        final_clip.close()
        for clip in clips:
            clip.close()

    return output_path, durations
