"""Concatenate per-item clips into the final vertical video."""

import os
from pathlib import Path
from typing import Sequence

from moviepy.editor import concatenate_videoclips

import config
from models import Item
from utils.paths import VIDEO_OUTPUT_DIR, video_output_path

from .utils import build_item_clip


def generate_video_short(items: Sequence[Item]) -> Path:
    """Render a 1080x1920 video from the titled images and narration on disk.

    Each item shows its images in sequence over its narration, with a short
    silence before and after, and a slow zoom on every image.
    """
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = video_output_path()

    clips = [
        build_item_clip(item_number, item)
        for item_number, item in enumerate(items, start=1)
    ]

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

    return output_path
