"""Single source of truth for every tunable constant in the pipeline.

Each value may be overridden by an environment variable of the same name, so
you can experiment (different model, higher concurrency, faster encode) without
editing code. Values are read at import time.

`MODEL_TIER` is the coarse switch: it sets the text and image models together,
and any variable you set yourself still wins over what the tier chose.
"""

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be a whole number, got {raw!r}"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"Environment variable {name} must be greater than zero, got {value}"
        )
    return value


# --- Model tier ----------------------------------------------------------
# One switch between the cheap models used to iterate on the pipeline and the
# expensive ones used to render a video worth publishing. Every constant a
# tier sets can still be pinned individually by its own environment variable,
# which always wins over the tier.
_MODEL_TIERS: dict[str, dict[str, Any]] = {
    "draft": {
        "TEXT_MODEL": "gpt-4.1-mini",
        "TEXT_TEMPERATURE": 0.7,
        "IMAGE_MODEL": "gpt-image-1",
        "IMAGE_SIZE": "1024x1024",
        "IMAGE_QUALITY": "medium",
    },
    "quality": {
        # gpt-5.5 reasons before it writes, which is what buys the better
        # script. It also rejects every temperature but its own default, so
        # the tier leaves the temperature unset and we send no such argument.
        "TEXT_MODEL": "gpt-5.5",
        "TEXT_TEMPERATURE": None,
        "IMAGE_MODEL": "gpt-image-2",
        # Portrait, because compose_frames scales the drawing to the full
        # 1080 width and centres it: a square drawing fills barely half the
        # 1920-tall frame and leaves the rest as blurred filler.
        "IMAGE_SIZE": "1024x1536",
        "IMAGE_QUALITY": "high",
    },
}


def tier_names() -> tuple[str, ...]:
    """Every tier `MODEL_TIER` accepts."""
    return tuple(_MODEL_TIERS)


def tier_values(tier: str) -> dict[str, Any]:
    """The constants `tier` stands for, or raise if it names no tier.

    Lower-case on purpose: `effective_config()` collects the module's
    upper-case names, and the tier table is machinery, not a setting.
    """
    try:
        return dict(_MODEL_TIERS[tier])
    except KeyError:
        raise ValueError(
            f"MODEL_TIER must be one of {', '.join(_MODEL_TIERS)}, got {tier!r}"
        ) from None


MODEL_TIER = _env_str("MODEL_TIER", "draft")
_tier = tier_values(MODEL_TIER)

# --- OpenAI models -------------------------------------------------------
# The text model must support JSON schema structured outputs, which is what
# lets us drop the old markdown-fence-stripping hack.
TEXT_MODEL = _env_str("TEXT_MODEL", _tier["TEXT_MODEL"])
# None means "send no temperature at all" - see the quality tier above.
TEXT_TEMPERATURE: float | None = _tier["TEXT_TEMPERATURE"]

# gpt-4o-mini-tts is the model that actually honours the `instructions`
# parameter. The old tts-1 silently ignored it, and tts-1-hd still does, so
# there is no higher tier to move the narration up to.
TTS_MODEL = _env_str("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = _env_str("TTS_VOICE", "ash")
TTS_INSTRUCTIONS = (
    "Speak in an engaging tone that would be informative and interesting for a "
    "YouTube video. Use a professional, conversational style."
)

IMAGE_MODEL = _env_str("IMAGE_MODEL", _tier["IMAGE_MODEL"])
IMAGE_SIZE = _env_str("IMAGE_SIZE", _tier["IMAGE_SIZE"])
IMAGE_QUALITY = _env_str("IMAGE_QUALITY", _tier["IMAGE_QUALITY"])

# The fixed look every generated frame shares. Prepended to every image
# prompt, in front of the script's style sheet.
STORYBOARD_STYLE = _env_str(
    "STORYBOARD_STYLE",
    "Black ink outline drawing filled with flat, bright colour on a plain "
    "white background. Simply drawn people with slim limbs and rounded "
    "heads, carrying the few features that make a person recognisable: skin "
    "tone, hair shape and colour, facial hair, glasses or headwear, and "
    "signature clothing. Clean even line weight, solid flat colour fills "
    "with no shading or gradients, no text or lettering.",
)

# --- Pipeline shape ------------------------------------------------------
# How long a script should run, and how long one image holds. Image count is
# a consequence of narration length, not a knob: see utils/timing.py.
TARGET_VIDEO_SECONDS = _env_int("TARGET_VIDEO_SECONDS", 85)
SECONDS_PER_IMAGE = 2.5

# Constants for estimating section narration duration and the script's word
# budget. Both were solved from real TTS renders, and must be re-solved if you
# change TTS_VOICE or TTS_INSTRUCTIONS.
#
# Sections are spoken as continuous paragraphs. Shots within a section run at
# roughly SECONDS_PER_IMAGE each, so shot duration is not constrained by the
# pause term. Instead, the pause term is load-bearing for two reasons:
# (1) speaking_seconds() uses both to estimate how long a section takes to
#     narrate, and (2) the word budget calculation uses the pause to trim the
#     budget down by ~28% (from 268 to 193 words for 85 seconds), preventing
#     the generated script from overwhelming the available time. Without this
#     trim, a naive budget would cause the video to overshoot by ~40%.
NARRATION_WORDS_PER_SECOND = 3.15
NARRATION_SENTENCE_PAUSE_SECONDS = 1.6
MAX_CONCURRENT_REQUESTS = _env_int("MAX_CONCURRENT_REQUESTS", 4)
MAX_RETRIES = _env_int("MAX_RETRIES", 5)
RETRY_INITIAL_WAIT_SECONDS = 2.0
RETRY_MAX_WAIT_SECONDS = 60.0

# --- Video geometry (YouTube Shorts, 9:16) -------------------------------
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = _env_int("VIDEO_FPS", 24)
VIDEO_CODEC = "libx264"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_PRESET = _env_str("VIDEO_PRESET", "medium")
INTRO_SILENCE_SECONDS = 0.2
OUTRO_SILENCE_SECONDS = 0.5

# --- Frame composition ---------------------------------------------------
BACKGROUND_BLUR_RADIUS = 90
# The background blur is applied at 1/N scale and upscaled back. For a radius
# this large the result is visually identical and ~100x cheaper.
BLUR_DOWNSCALE_FACTOR = 10
BACKGROUND_OVERLAY_ALPHA = 128
