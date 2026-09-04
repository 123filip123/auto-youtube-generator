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
from models import Item
from utils.paths import audio_path, titled_image_path


def zoom_scale(t: float, segment_duration: float, end_scale: float) -> float:
    """Linear zoom from 1.0 to `end_scale`, clamped at both ends.

    Clamping matters: moviepy sometimes samples marginally outside [0, duration].
    """
    if segment_duration <= 0:
        return 1.0
    progress = min(max(t / segment_duration, 0.0), 1.0)
    return 1.0 + (end_scale - 1.0) * progress


def beat_weights(item: Item) -> list[float]:
    """How long each beat should hold, as the word count of its narration.

    TTS pace is close enough to uniform that word count is a good proxy for
    elapsed time, and it costs nothing. Items with no narration — every
    archive written before storyboards — weigh zero and fall back to an
    equal split.
    """
    return [float(len(beat.narration.split())) for beat in item.beats]


def segment_bounds(
    total_duration: float, weights: Sequence[float] | int
) -> list[tuple[float, float]]:
    """Split `total_duration` into (start, duration) pairs.

    `weights` may be a count, meaning that many equal segments, or a per-
    segment weight list. Equal weights produce exactly the even split, so a
    narrationless item behaves as it always did.
    """
    if isinstance(weights, int):
        weights = [1.0] * weights

    weights = list(weights)
    if not weights:
        raise ValueError("Need at least one image per item, got 0")

    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0] * len(weights)
        total_weight = float(len(weights))

    bounds: list[tuple[float, float]] = []
    start = 0.0
    for weight in weights:
        duration = total_duration * weight / total_weight
        bounds.append((start, duration))
        start += duration
    return bounds


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


def build_item_clip(item_number: int, item: Item):
    """One item: its story frames in sequence, over its narration."""
    audio, total_duration = build_item_audio(item_number)

    layers = [build_background_clip(total_duration)]
    for beat_number, (start, duration) in enumerate(
        segment_bounds(total_duration, beat_weights(item)), start=1
    ):
        layers.append(
            build_image_clip(
                titled_image_path(item_number, beat_number), duration, start
            )
        )

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
