from pathlib import Path

import pytest

from models import Item, load_items
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_to_generated_data,
)
from utils.paths import ensure_output_dirs


@pytest.fixture
def populated_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    Path("outputs/audio_output/item_01.mp3").write_bytes(b"audio")
    Path("outputs/image_output/item_01_prompt_01.png").write_bytes(b"image")
    Path("outputs/titled_image_output/item_01_prompt_01_short.png").write_bytes(b"tit")
    Path("outputs/video_output/final_video_short.mp4").write_bytes(b"video")
    return tmp_path


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def test_creates_a_slugged_folder(populated_outputs):
    folder = save_to_generated_data("Top 5: Extinct Animals!", one_item())
    assert folder == Path("generated_data/top_5_extinct_animals")
    assert folder.is_dir()


def test_archives_the_item_list(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert load_items(folder / "list_items.json") == one_item()


def test_archives_audio(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "audio" / "item_01.mp3").read_bytes() == b"audio"


def test_archives_images(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "images" / "item_01_prompt_01.png").read_bytes() == b"image"


def test_archives_titled_images(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "titled_images" / "item_01_prompt_01_short.png").exists()


def test_archives_the_final_video(populated_outputs):
    # The old pipeline ran this before the video existed, so it never got saved.
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "final_video_short.mp4").read_bytes() == b"video"


def test_tolerates_a_missing_video(populated_outputs):
    Path("outputs/video_output/final_video_short.mp4").unlink()
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert folder.is_dir()
    assert not (folder / "final_video_short.mp4").exists()


def test_is_idempotent(populated_outputs):
    save_to_generated_data("Extinct Animals", one_item())
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "audio" / "item_01.mp3").exists()


def test_falls_back_to_a_timestamp_for_an_unusable_topic(populated_outputs):
    folder = save_to_generated_data("!!!", one_item())
    assert folder.parent == Path("generated_data")
    assert folder.is_dir()
