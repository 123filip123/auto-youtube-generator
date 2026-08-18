"""Archive one finished run into `generated_data/<topic-slug>/`."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence

from models import Item, save_items
from utils.paths import (
    ARCHIVED_LIST_FILENAME,
    AUDIO_OUTPUT_DIR,
    GENERATED_DATA_ROOT,
    IMAGE_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    VIDEO_FILENAME,
    slugify,
    video_output_path,
)


def _copy_tree(source: Path, destination: Path, suffix: str) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    if not source.is_dir():
        return copied
    for entry in sorted(source.iterdir()):
        if entry.is_file() and entry.suffix == suffix:
            shutil.copy2(entry, destination / entry.name)
            copied += 1
    return copied


def save_to_generated_data(topic: str, items: Sequence[Item]) -> Path:
    """Copy this run's list, audio, images, titled images and video into an archive.

    Must run *after* the video is rendered — the previous pipeline called this
    before video assembly, so the archive never contained the finished video.
    """
    slug = slugify(topic)
    if slug == "untitled":
        slug = datetime.now().strftime("%Y%m%d_%H%M%S")

    folder = GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)

    save_items(items, folder / ARCHIVED_LIST_FILENAME)

    audio_count = _copy_tree(AUDIO_OUTPUT_DIR, folder / "audio", ".mp3")
    image_count = _copy_tree(IMAGE_OUTPUT_DIR, folder / "images", ".png")
    titled_count = _copy_tree(
        TITLED_IMAGE_OUTPUT_DIR, folder / "titled_images", ".png"
    )

    video = video_output_path()
    if video.exists():
        shutil.copy2(video, folder / VIDEO_FILENAME)

    print(
        f"\nArchived to {folder}: {audio_count} audio, {image_count} images, "
        f"{titled_count} titled images"
        + (", 1 video" if video.exists() else ", no video")
    )
    return folder
