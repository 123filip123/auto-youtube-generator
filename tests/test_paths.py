from pathlib import Path

import pytest

from utils import paths


def test_image_path_is_zero_padded():
    assert paths.image_path(1, 2) == Path("outputs/image_output/item_01_prompt_02.png")


def test_image_path_handles_double_digits():
    assert paths.image_path(12, 10) == Path("outputs/image_output/item_12_prompt_10.png")


def test_audio_path_is_zero_padded():
    assert paths.audio_path(3) == Path("outputs/audio_output/item_03.mp3")


def test_titled_image_path_has_short_suffix():
    assert paths.titled_image_path(5, 1) == Path(
        "outputs/titled_image_output/item_05_prompt_01_short.png"
    )


def test_list_items_path():
    assert paths.list_items_path() == Path(
        "outputs/json_output/list_items_with_prompts.json"
    )


def test_video_output_path():
    assert paths.video_output_path() == Path("outputs/video_output/final_video_short.mp4")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Top 5 Extinct Animals", "top_5_extinct_animals"),
        ("Most Delicious Sandwiches", "most_delicious_sandwiches"),
        ("Top 5: Extinct Animals!", "top_5_extinct_animals"),
        ("  spaced   out  ", "spaced_out"),
        ("!!!", "untitled"),
        ("", "untitled"),
    ],
)
def test_slugify(raw, expected):
    assert paths.slugify(raw) == expected


def test_generated_data_dir():
    assert paths.generated_data_dir("Top 5 Extinct Animals") == Path(
        "generated_data/top_5_extinct_animals"
    )


def test_ensure_output_dirs_creates_everything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths.ensure_output_dirs()
    for directory in paths.ALL_OUTPUT_DIRS:
        assert directory.is_dir()


def test_ensure_output_dirs_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths.ensure_output_dirs()
    paths.ensure_output_dirs()
    assert paths.AUDIO_OUTPUT_DIR.is_dir()
