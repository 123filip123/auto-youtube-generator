"""Read `generated_data/` into payloads the archive browser can render.

Filenames are the join key: `images/section_02_shot_01.png` belongs to
section 2. Every subdirectory is treated as optional, since an archive can be
missing composed frames or a video (or, mid-run, everything but the script).
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import InvalidScriptError, load_script
from utils.paths import ARCHIVED_SCRIPT_FILENAME, GENERATED_DATA_ROOT, VIDEO_FILENAME

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


def _names_with_prefix(directory: Path, prefix: str, suffix: str) -> list[str]:
    if not directory.is_dir():
        return []
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
        listing = folder / ARCHIVED_SCRIPT_FILENAME
        section_count = 0
        if listing.is_file():
            try:
                section_count = len(load_script(listing).sections)
            except (InvalidScriptError, OSError):
                section_count = 0
        summaries.append(
            {
                "slug": folder.name,
                "section_count": section_count,
                "image_count": _count_files(folder / "images", ".png"),
                "audio_count": _count_files(folder / "audio", ".mp3"),
                "has_video": (folder / VIDEO_FILENAME).is_file(),
                "modified_at": _modified_at(folder),
            }
        )

    summaries.sort(key=lambda summary: summary["modified_at"], reverse=True)
    return summaries


def archive_detail(slug: str) -> dict[str, Any]:
    """One archive's sections with a media URL for every file that exists."""
    folder = _archive_dir(slug)

    listing = folder / ARCHIVED_SCRIPT_FILENAME
    if not listing.is_file():
        raise ArchiveNotFoundError(slug)
    try:
        script = load_script(listing)
    except (InvalidScriptError, OSError) as exc:
        raise ArchiveNotFoundError(slug) from exc

    payload_sections: list[dict[str, Any]] = []
    for section_number, section in enumerate(script.sections, start=1):
        audio_name = f"section_{section_number:02d}.mp3"
        has_audio = (folder / "audio" / audio_name).is_file()
        payload_sections.append(
            {
                "label": section.label,
                "narration": section.narration,
                "prompts": list(section.prompts),
                "image_urls": [
                    _url(slug, "images", name)
                    for name in _names_with_prefix(
                        folder / "images", f"section_{section_number:02d}_", ".png"
                    )
                ],
                "composed_image_urls": [
                    _url(slug, "composed_images", name)
                    for name in _names_with_prefix(
                        folder / "composed_images",
                        f"composed_section_{section_number:02d}_",
                        ".png",
                    )
                ],
                "audio_url": _url(slug, "audio", audio_name) if has_audio else None,
            }
        )

    video = folder / VIDEO_FILENAME
    return {
        "slug": slug,
        "topic": script.topic,
        "title": script.title,
        "style": script.style,
        "video_url": _url(slug, VIDEO_FILENAME) if video.is_file() else None,
        "sections": payload_sections,
    }
