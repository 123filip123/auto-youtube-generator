import json

import pytest

from api.archives import ArchiveNotFoundError, archive_detail, list_archives


def build_archive(root, slug, *, with_titled=True, with_video=True):
    folder = root / "generated_data" / slug
    (folder / "images").mkdir(parents=True)
    (folder / "audio").mkdir(parents=True)
    (folder / "list_items.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Dodo",
                        "description": "A bird.",
                        "image_prompts": ["a", "b"],
                    }
                ]
            }
        )
    )
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"x")
    (folder / "images" / "item_01_prompt_02.png").write_bytes(b"x")
    (folder / "audio" / "item_01.mp3").write_bytes(b"x")
    if with_titled:
        (folder / "titled_images").mkdir()
        (folder / "titled_images" / "item_01_prompt_01_short.png").write_bytes(b"x")
    if with_video:
        (folder / "final_video_short.mp4").write_bytes(b"x")
    return folder


def test_list_archives_summarises_each_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "birds")

    (summary,) = list_archives()
    assert summary["slug"] == "birds"
    assert summary["item_count"] == 1
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

    (item,) = detail["items"]
    assert item["title"] == "Dodo"
    assert item["image_urls"] == [
        "/media/generated_data/birds/images/item_01_prompt_01.png",
        "/media/generated_data/birds/images/item_01_prompt_02.png",
    ]
    assert item["titled_image_urls"] == [
        "/media/generated_data/birds/titled_images/item_01_prompt_01_short.png"
    ]
    assert item["audio_url"] == "/media/generated_data/birds/audio/item_01.mp3"


def test_archive_detail_tolerates_an_older_archive(tmp_path, monkeypatch):
    # The archives already on disk have no titled_images/ and no video.
    monkeypatch.chdir(tmp_path)
    build_archive(tmp_path, "old", with_titled=False, with_video=False)

    detail = archive_detail("old")
    assert detail["video_url"] is None
    assert detail["items"][0]["titled_image_urls"] == []


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
