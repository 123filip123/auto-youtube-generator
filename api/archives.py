"""Read `generated_data/` into payloads the archive browser can render.

Filenames are the join key: `images/item_04_prompt_02.png` belongs to item 4.
Older archives were written before titled images and the video were copied in,
so every subdirectory is treated as optional.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import InvalidItemsError, load_items
from utils.paths import ARCHIVED_LIST_FILENAME, GENERATED_DATA_ROOT, VIDEO_FILENAME

MEDIA_PREFIX = "/media/generated_data"

# `slugify` only ever emits lowercase alphanumerics and underscores. Anything
# else is either a stray directory or a traversal attempt.
_VALID_SLUG = re.compile(r"^[a-z0-9_]+$")


class ArchiveNotFoundError(KeyError):
    """No readable archive with that slug exists."""


def _url(slug: str, *parts: str) -> str:
    return "/".join((MEDIA_PREFIX, slug, *parts))


def _modified_at(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return stamp.isoformat()


def _count_files(directory: Path, suffix: str) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for entry in directory.iterdir() if entry.suffix == suffix)


def _names_for_item(directory: Path, item_number: int, suffix: str) -> list[str]:
    if not directory.is_dir():
        return []
    prefix = f"item_{item_number:02d}_"
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix == suffix and entry.name.startswith(prefix)
    )


def _archive_dir(slug: str) -> Path:
    if not _VALID_SLUG.match(slug):
        raise ArchiveNotFoundError(slug)
    folder = GENERATED_DATA_ROOT / slug
    if not folder.is_dir():
        raise ArchiveNotFoundError(slug)
    return folder


def list_archives() -> list[dict[str, Any]]:
    """Summarise every archive folder, newest first."""
    if not GENERATED_DATA_ROOT.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for folder in GENERATED_DATA_ROOT.iterdir():
        if not folder.is_dir() or not _VALID_SLUG.match(folder.name):
            continue
        listing = folder / ARCHIVED_LIST_FILENAME
        try:
            items = load_items(listing) if listing.is_file() else []
        except (InvalidItemsError, OSError):
            items = []
        summaries.append(
            {
                "slug": folder.name,
                "item_count": len(items),
                "image_count": _count_files(folder / "images", ".png"),
                "audio_count": _count_files(folder / "audio", ".mp3"),
                "has_video": (folder / VIDEO_FILENAME).is_file(),
                "modified_at": _modified_at(folder),
            }
        )

    summaries.sort(key=lambda summary: summary["modified_at"], reverse=True)
    return summaries


def archive_detail(slug: str) -> dict[str, Any]:
    """One archive's items with a media URL for every file that exists."""
    folder = _archive_dir(slug)

    listing = folder / ARCHIVED_LIST_FILENAME
    if not listing.is_file():
        raise ArchiveNotFoundError(slug)
    try:
        items = load_items(listing)
    except (InvalidItemsError, OSError) as exc:
        raise ArchiveNotFoundError(slug) from exc

    payload_items: list[dict[str, Any]] = []
    for item_number, item in enumerate(items, start=1):
        audio_name = f"item_{item_number:02d}.mp3"
        has_audio = (folder / "audio" / audio_name).is_file()
        payload_items.append(
            {
                "title": item.title,
                "description": item.description,
                "style": item.style,
                "beats": [
                    {"narration": beat.narration, "prompt": beat.prompt}
                    for beat in item.beats
                ],
                "image_prompts": list(item.image_prompts),
                "image_urls": [
                    _url(slug, "images", name)
                    for name in _names_for_item(folder / "images", item_number, ".png")
                ],
                "titled_image_urls": [
                    _url(slug, "titled_images", name)
                    for name in _names_for_item(
                        folder / "titled_images", item_number, ".png"
                    )
                ],
                "audio_url": _url(slug, "audio", audio_name) if has_audio else None,
            }
        )

    video = folder / VIDEO_FILENAME
    return {
        "slug": slug,
        "video_url": _url(slug, VIDEO_FILENAME) if video.is_file() else None,
        "items": payload_items,
    }
