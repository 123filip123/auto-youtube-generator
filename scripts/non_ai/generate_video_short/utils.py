"""Assemble titled images and narration into per-item video clips."""

from pathlib import Path
from typing import Sequence

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoClip,
)
from PIL import Image

import config
from utils.paths import audio_path


def zoom_scale(t: float, segment_duration: float, end_scale: float) -> float:
    """Linear zoom from 1.0 to `end_scale`, clamped at both ends.

    Clamping matters: moviepy sometimes samples marginally outside [0, duration].
    """
    if segment_duration <= 0:
        return 1.0
    progress = min(max(t / segment_duration, 0.0), 1.0)
    return 1.0 + (end_scale - 1.0) * progress


def segment_bounds(total_duration: float, count: int) -> list[tuple[float, float]]:
    """Split `total_duration` into `count` (start, duration) pairs."""
    if count < 1:
        raise ValueError(f"Need at least one image per item, got {count}")
    segment = total_duration / count
    return [(index * segment, segment) for index in range(count)]


def build_background_clip(duration: float) -> ColorClip:
    return ColorClip(
        size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(255, 255, 255)
    ).set_duration(duration)


def build_image_clip(image_path: Path, segment_duration: float, start_time: float):
    """A still image that slowly zooms in over `segment_duration`.

    The source is decoded once and captured in the closure, so each frame costs
    exactly one BILINEAR resize instead of a decode plus a LANCZOS resize.
    """
    with Image.open(image_path) as opened:
        source = opened.convert("RGB")
    base_width, base_height = source.size

    def make_frame(t):
        scale = zoom_scale(t, segment_duration, config.ZOOM_END_SCALE)
        resized = source.resize(
            (round(base_width * scale), round(base_height * scale)),
            Image.Resampling.BILINEAR,
        )
        return np.asarray(resized)

    clip = VideoClip(make_frame, duration=segment_duration)
    return clip.set_position("center").set_start(start_time)


def build_item_audio(item_number: int) -> tuple[CompositeAudioClip, float]:
    """Narration padded with leading and trailing silence.

    Returns the clip and its total duration, so callers do not need to reopen
    the file just to measure it. The previous implementation opened the same
    mp3 four times per item.
    """
    voice = AudioFileClip(str(audio_path(item_number)))
    total_duration = (
        config.INTRO_SILENCE_SECONDS + voice.duration + config.OUTRO_SILENCE_SECONDS
    )
    padded = CompositeAudioClip(
        [voice.set_start(config.INTRO_SILENCE_SECONDS)]
    ).set_duration(total_duration)
    return padded, total_duration


def build_item_clip(item_number: int, frame_paths: Sequence[Path]):
    """One item: its titled frames in sequence, over its narration."""
    audio, total_duration = build_item_audio(item_number)

    layers = [build_background_clip(total_duration)]
    for frame_path, (start, duration) in zip(
        frame_paths, segment_bounds(total_duration, len(frame_paths))
    ):
        layers.append(build_image_clip(frame_path, duration, start))

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
