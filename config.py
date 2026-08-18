"""Single source of truth for every tunable constant in the pipeline.

Each value may be overridden by an environment variable of the same name, so
you can experiment (different model, higher concurrency, faster encode) without
editing code. Values are read at import time.
"""

import os

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


# --- OpenAI models -------------------------------------------------------
# gpt-4.1-mini supports JSON schema structured outputs, which is what lets us
# drop the old markdown-fence-stripping hack.
TEXT_MODEL = _env_str("TEXT_MODEL", "gpt-4.1-mini")
TEXT_TEMPERATURE = 0.7

# gpt-4o-mini-tts is the model that actually honours the `instructions`
# parameter. The old tts-1 silently ignored it.
TTS_MODEL = _env_str("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = _env_str("TTS_VOICE", "ash")
TTS_INSTRUCTIONS = (
    "Speak in an engaging tone that would be informative and interesting for a "
    "YouTube video. Use a professional, conversational style."
)

IMAGE_MODEL = _env_str("IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = _env_str("IMAGE_SIZE", "1024x1024")
IMAGE_QUALITY = _env_str("IMAGE_QUALITY", "medium")

# --- Pipeline shape ------------------------------------------------------
IMAGE_PROMPTS_PER_ITEM = _env_int("IMAGE_PROMPTS_PER_ITEM", 3)
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
ZOOM_END_SCALE = 1.2

# --- Titled image rendering ---------------------------------------------
TITLE_FONT_SIZE = 120
TITLE_LINE_SPACING = 10
TITLE_SIDE_MARGIN = 50
TITLE_GAP_BELOW_IMAGE = 220
TITLE_COLOR = "black"
BACKGROUND_BLUR_RADIUS = 90
# The background blur is applied at 1/N scale and upscaled back. For a radius
# this large the result is visually identical and ~100x cheaper.
BLUR_DOWNSCALE_FACTOR = 10
BACKGROUND_OVERLAY_ALPHA = 128
