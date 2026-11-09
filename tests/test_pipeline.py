from pathlib import Path

import pytest
from PIL import Image

from models import Item
from pipeline import PipelineError, missing_media, missing_titled_images
from utils.paths import audio_path, ensure_output_dirs, image_path, titled_image_path


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def write_media(items, *, skip=()):
    for item_number, item in enumerate(items, start=1):
        if ("audio", item_number) not in skip:
            audio_path(item_number).write_bytes(b"audio")
        for prompt_number in range(1, len(item.image_prompts) + 1):
            if ("image", item_number, prompt_number) in skip:
                continue
            image_path(item_number, prompt_number).write_bytes(b"image")


def test_missing_media_is_empty_when_everything_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item())
    assert missing_media(one_item()) == []


def test_missing_media_tolerates_a_missing_image(tmp_path, monkeypatch):
    # A rejected image leaves the item with fewer pictures, not a failed run.
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item(), skip=[("image", 1, 2)])
    assert missing_media(one_item()) == []


def test_missing_media_reports_a_missing_audio_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item(), skip=[("audio", 1)])
    assert missing_media(one_item()) == [audio_path(1)]


def test_missing_media_reports_an_empty_audio_file(tmp_path, monkeypatch):
    # A zero-byte file would pass an exists() check but break the renderer.
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item())
    audio_path(1).write_bytes(b"")
    assert audio_path(1) in missing_media(one_item())


def test_missing_titled_images_expects_a_placeholder_for_an_imageless_item(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    assert missing_titled_images(one_item()) == [titled_image_path(1, 1)]


def test_missing_titled_images_reports_gaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item())
    titled_image_path(1, 1).write_bytes(b"x")
    missing = missing_titled_images(one_item())
    assert titled_image_path(1, 2) in missing
    assert titled_image_path(1, 1) not in missing


def test_pipeline_error_is_a_runtime_error():
    assert issubclass(PipelineError, RuntimeError)

def test_media_job_total_counts_audio_plus_every_image():
    from pipeline import media_job_total

    items = [Item("A", "d", ("p1", "p2")), Item("B", "d", ("p1",))]
    # 2 narrations + 3 images
    assert media_job_total(items) == 5


def test_titled_job_total_counts_every_generated_image(tmp_path, monkeypatch):
    from pipeline import titled_job_total

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    items = [Item("A", "d", ("p1", "p2", "p3")), Item("B", "d", ("p1",))]
    write_media(items, skip=[("image", 1, 2)])
    assert titled_job_total(items) == 3


def test_titled_job_total_counts_one_placeholder_for_an_imageless_item(
    tmp_path, monkeypatch
):
    from pipeline import titled_job_total

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    items = [Item("A", "d", ("p1", "p2"))]
    write_media(items, skip=[("image", 1, 1), ("image", 1, 2)])
    assert titled_job_total(items) == 1


def test_generate_items_stage_saves_the_list_and_logs(tmp_path, monkeypatch):
    import json

    from pipeline import generate_items_stage
    from utils.paths import list_items_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pipeline.generate_list",
        lambda topic, num_items, client=None: [Item("Dodo", "A bird.", ("a", "b", "c"))],
    )

    lines = []
    items = generate_items_stage("birds", 1, log=lines.append)

    assert [item.title for item in items] == ["Dodo"]
    saved = json.loads(list_items_path().read_text())
    assert saved["items"][0]["title"] == "Dodo"
    assert any("Dodo" in line for line in lines)


def test_generate_media_stage_raises_when_an_asset_is_missing(tmp_path, monkeypatch):
    from pipeline import generate_media_stage

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    monkeypatch.setattr("pipeline.image_jobs", lambda items, client=None: [])
    monkeypatch.setattr("pipeline.audio_jobs", lambda items, client=None: [])

    with pytest.raises(PipelineError, match="Media generation"):
        generate_media_stage(one_item(), log=lambda _: None)


def test_generate_media_stage_forwards_asset_results(tmp_path, monkeypatch):
    from pipeline import generate_media_stage

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    items = one_item()

    monkeypatch.setattr(
        "pipeline.image_jobs", lambda items, client=None: [("image 1", lambda: None)]
    )
    monkeypatch.setattr(
        "pipeline.audio_jobs",
        lambda items, client=None: [("audio 1", lambda: write_media(items))],
    )

    seen = []
    generate_media_stage(items, log=lambda _: None, on_asset=seen.append)
    assert sorted(r.label for r in seen) == ["audio 1", "image 1"]


def stub_media_jobs(monkeypatch, items):
    """Media jobs that just write placeholder files for `items`."""
    monkeypatch.setattr("pipeline.image_jobs", lambda items, client=None: [])
    monkeypatch.setattr(
        "pipeline.audio_jobs",
        lambda _, client=None: [("audio", lambda: write_media(items))],
    )


def test_generate_media_stage_clears_the_previous_runs_media(tmp_path, monkeypatch):
    # A previous run with more items left item 2's files behind; the archive
    # would copy them into this run's folder.
    from pipeline import generate_media_stage

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    leftovers = [Item("Old", "d", ("a",)), Item("Older", "d", ("a",))]
    write_media(leftovers)
    stub_media_jobs(monkeypatch, one_item())

    generate_media_stage(one_item(), log=lambda _: None)

    assert not image_path(2, 1).exists()
    assert not audio_path(2).exists()
    assert audio_path(1).exists()


def test_titled_stage_clears_the_previous_runs_frames(tmp_path, monkeypatch):
    from pipeline import render_titled_images_stage

    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    items = one_item()
    Image.new("RGB", (64, 64)).save(image_path(1, 1))
    stale = titled_image_path(1, 3)
    stale.write_bytes(b"old frame")

    render_titled_images_stage(items, log=lambda _: None)

    assert titled_image_path(1, 1).exists()
    assert not stale.exists()
