import json

import pytest

from api import archives
from api.archives import ArchiveNotFoundError, archive_detail, list_archives
from models import Script, Section, save_script
from utils.paths import ARCHIVED_SCRIPT_FILENAME, GENERATED_DATA_ROOT, VIDEO_FILENAME


def _script():
    return Script(
        topic="birds",
        title="Two Extinct Birds",
        style="A tall flightless bird.",
        sections=(
            Section(
                "HOOK", "A flightless bird. It is extinct.", ("a", "b"), 0.0, 5.0
            ),
        ),
    )


def build_archive(root, slug, *, with_composed=True, with_video=True):
    folder = root / "generated_data" / slug
    (folder / "images").mkdir(parents=True)
    (folder / "audio").mkdir(parents=True)
    save_script(_script(), folder / ARCHIVED_SCRIPT_FILENAME)
    (folder / "images" / "section_01_shot_01.png").write_bytes(b"x")
    (folder / "images" / "section_01_shot_02.png").write_bytes(b"x")
    (folder / "audio" / "section_01.mp3").write_bytes(b"x")
    if with_composed:
        (folder / "composed_images").mkdir()
        (folder / "composed_images" / "composed_section_01_shot_01.png").write_bytes(
            b"x"
        )
    if with_video:
        (folder / "final_video_short.mp4").write_bytes(b"x")
    return folder


def test_list_archives_summarises_each_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")

    (summary,) = list_archives()
    assert summary["slug"] == "birds"
    assert summary["section_count"] == 1
    assert summary["image_count"] == 2
    assert summary["audio_count"] == 1
    assert summary["has_video"] is True
    assert summary["modified_at"]


def test_list_archives_is_empty_when_there_is_no_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert list_archives() == []


def test_archive_detail_builds_media_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")

    detail = archive_detail("birds")
    assert detail["video_url"] == "/media/generated_data/birds/final_video_short.mp4"
    assert detail["title"] == "Two Extinct Birds"
    assert detail["style"] == "A tall flightless bird."

    (section,) = detail["sections"]
    assert section["label"] == "HOOK"
    assert section["image_urls"] == [
        "/media/generated_data/birds/images/section_01_shot_01.png",
        "/media/generated_data/birds/images/section_01_shot_02.png",
    ]
    assert section["composed_image_urls"] == [
        "/media/generated_data/birds/composed_images/composed_section_01_shot_01.png"
    ]
    assert section["audio_url"] == "/media/generated_data/birds/audio/section_01.mp3"


def test_archive_detail_tolerates_a_run_with_no_composed_frames_or_video(
    tmp_path, monkeypatch
):
    # An archive from a run that hasn't finished composing yet, say.
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "old", with_composed=False, with_video=False)

    detail = archive_detail("old")
    assert detail["video_url"] is None
    assert detail["sections"][0]["composed_image_urls"] == []


def test_archive_detail_rejects_an_unknown_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ArchiveNotFoundError):
        archive_detail("missing")


@pytest.mark.parametrize("slug", ["../secrets", "birds/../..", "a b", "Birds"])
def test_archive_detail_rejects_a_malformed_slug(tmp_path, monkeypatch, slug):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")
    with pytest.raises(ArchiveNotFoundError):
        archive_detail(slug)


def test_archive_detail_exposes_prompts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "generated_data" / "birds"
    folder.mkdir(parents=True)
    save_script(
        Script(
            topic="birds",
            title="Moa",
            style="A tall bird.",
            sections=(Section("HOOK", "A very tall bird.", ("the bird alone",)),),
        ),
        folder / ARCHIVED_SCRIPT_FILENAME,
    )

    detail = archive_detail("birds")
    assert detail["style"] == "A tall bird."
    assert detail["sections"][0]["narration"] == "A very tall bird."
    assert detail["sections"][0]["prompts"] == ["the bird alone"]


def write_legacy_archive(root, slug="old_run"):
    """An archive in the pre-migration shape: list_items.json, item_* filenames."""
    folder = root / GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "list_items.json").write_text(
        json.dumps([{"title": "Dodo", "description": "A bird.", "image_prompts": ["p"]}])
    )
    (folder / "images").mkdir(exist_ok=True)
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"png")
    (folder / VIDEO_FILENAME).write_bytes(b"mp4")
    return folder


def test_a_legacy_archive_is_listed_and_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_legacy_archive(tmp_path)
    summary = archives.list_archives()[0]
    assert summary["legacy"] is True
    assert summary["section_count"] == 0
    assert summary["image_count"] == 1
    assert summary["has_video"] is True


def test_a_legacy_archive_detail_keeps_its_video_and_does_not_raise(tmp_path, monkeypatch):
    """The whole point: an old run must not vanish from the browser."""
    monkeypatch.chdir(tmp_path)
    write_legacy_archive(tmp_path)
    detail = archives.archive_detail("old_run")
    assert detail["legacy"] is True
    assert detail["sections"] == []
    assert detail["video_url"].endswith(VIDEO_FILENAME)


def test_a_current_archive_is_not_flagged_legacy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "wolves")
    assert archives.list_archives()[0]["legacy"] is False
    assert archives.archive_detail("wolves")["legacy"] is False


def test_an_archive_with_unreadable_script_is_treated_as_legacy(tmp_path, monkeypatch):
    """Corrupt JSON must degrade to legacy, not 404 the whole archive."""
    monkeypatch.chdir(tmp_path)
    folder = build_archive(tmp_path, "wolves")
    (folder / ARCHIVED_SCRIPT_FILENAME).write_text("{ not json")
    assert archives.archive_detail("wolves")["legacy"] is True


def test_an_unknown_slug_still_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(archives.ArchiveNotFoundError):
        archives.archive_detail("nope")


def test_a_traversal_slug_is_still_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(archives.ArchiveNotFoundError):
        archives.archive_detail("../etc")


def test_sections_carry_their_timings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "wolves")
    section = archives.archive_detail("wolves")["sections"][0]
    assert section["start"] == 0.0
    assert section["end"] == 5.0
