"""Every output directory and filename the pipeline produces.

Paths are deliberately relative to the current working directory so tests can
chdir into a temp directory and exercise real filesystem behaviour.
"""

import re
from pathlib import Path

OUTPUTS_ROOT = Path("outputs")
AUDIO_OUTPUT_DIR = OUTPUTS_ROOT / "audio_output"
IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "image_output"
JSON_OUTPUT_DIR = OUTPUTS_ROOT / "json_output"
TITLED_IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "titled_image_output"
COMPOSED_IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "composed_image_output"
VIDEO_OUTPUT_DIR = OUTPUTS_ROOT / "video_output"

GENERATED_DATA_ROOT = Path("generated_data")

ALL_OUTPUT_DIRS = (
    AUDIO_OUTPUT_DIR,
    IMAGE_OUTPUT_DIR,
    JSON_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    COMPOSED_IMAGE_OUTPUT_DIR,
    VIDEO_OUTPUT_DIR,
)

LIST_ITEMS_FILENAME = "list_items_with_prompts.json"
ARCHIVED_LIST_FILENAME = "list_items.json"
ARCHIVED_SCRIPT_FILENAME = "script.json"
VIDEO_FILENAME = "final_video_short.mp4"
SCRIPT_FILENAME = "script.json"

_SLUG_SEPARATORS = re.compile(r"[^a-z0-9]+")


def ensure_output_dirs() -> None:
    """Create every output directory. Safe to call repeatedly."""
    for directory in ALL_OUTPUT_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def image_path(item_number: int, prompt_number: int) -> Path:
    return IMAGE_OUTPUT_DIR / f"item_{item_number:02d}_prompt_{prompt_number:02d}.png"


def audio_path(item_number: int) -> Path:
    return AUDIO_OUTPUT_DIR / f"item_{item_number:02d}.mp3"


def titled_image_path(item_number: int, prompt_number: int) -> Path:
    return (
        TITLED_IMAGE_OUTPUT_DIR
        / f"item_{item_number:02d}_prompt_{prompt_number:02d}_short.png"
    )


def list_items_path() -> Path:
    return JSON_OUTPUT_DIR / LIST_ITEMS_FILENAME


def video_output_path() -> Path:
    return VIDEO_OUTPUT_DIR / VIDEO_FILENAME


def slugify(text: str) -> str:
    """Turn a topic into a filesystem-safe folder name.

    Runs of non-alphanumeric characters collapse to a single underscore and
    leading/trailing underscores are stripped, so "Top 5: Extinct Animals!"
    becomes "top_5_extinct_animals".
    """
    slug = _SLUG_SEPARATORS.sub("_", text.lower()).strip("_")
    return slug or "untitled"


def generated_data_dir(topic: str) -> Path:
    return GENERATED_DATA_ROOT / slugify(topic)


def section_image_path(section_number: int, shot_number: int) -> Path:
    return (
        IMAGE_OUTPUT_DIR
        / f"section_{section_number:02d}_shot_{shot_number:02d}.png"
    )


def section_audio_path(section_number: int) -> Path:
    return AUDIO_OUTPUT_DIR / f"section_{section_number:02d}.mp3"


def composed_image_path(section_number: int, shot_number: int) -> Path:
    return (
        COMPOSED_IMAGE_OUTPUT_DIR
        / f"composed_section_{section_number:02d}_shot_{shot_number:02d}.png"
    )


def script_path() -> Path:
    return JSON_OUTPUT_DIR / SCRIPT_FILENAME
