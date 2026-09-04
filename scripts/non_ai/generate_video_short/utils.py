"""Assemble titled images and narration into per-item video clips."""

from pathlib import Path
from typing import Sequence

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
)
from PIL import Image

import config
from models import Item, Section
from utils.paths import (
    audio_path,
    composed_image_path,
    section_audio_path,
    titled_image_path,
)


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
        raise ValueError("Need at least one image per section, got 0")

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
    """A still image held for `segment_duration`.

    Decoded once here rather than once per frame, and handed over as an array
    so the clip is RGB whatever the file on disk happens to be.
    """
    with Image.open(image_path) as opened:
        frame = np.asarray(opened.convert("RGB"))

    clip = ImageClip(frame, duration=segment_duration)
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


def build_section_audio(
    section_number: int, *, is_first: bool, is_last: bool
) -> tuple[CompositeAudioClip, float]:
    """One section's narration, padded only where the video actually ends.

    Padding every section — as the per-item version did — puts a silent gap at
    every interior boundary, which is what makes a concatenation sound like
    separate clips rather than one continuous video.
    """
    voice = AudioFileClip(str(section_audio_path(section_number)))
    lead = config.INTRO_SILENCE_SECONDS if is_first else 0.0
    tail = config.OUTRO_SILENCE_SECONDS if is_last else 0.0
    total_duration = lead + voice.duration + tail
    padded = CompositeAudioClip([voice.set_start(lead)]).set_duration(total_duration)
    return padded, total_duration


def build_section_clip(
    section_number: int, section: Section, *, is_first: bool, is_last: bool
):
    """One section: its shots held in equal turns over its narration."""
    audio, total_duration = build_section_audio(
        section_number, is_first=is_first, is_last=is_last
    )

    layers = [build_background_clip(total_duration)]
    for shot_number, (start, duration) in enumerate(
        segment_bounds(total_duration, len(section.prompts)), start=1
    ):
        layers.append(
            build_image_clip(
                composed_image_path(section_number, shot_number), duration, start
            )
        )

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
