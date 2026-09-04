from pathlib import Path

import pytest

from utils import paths


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


from utils.paths import (
    COMPOSED_IMAGE_OUTPUT_DIR,
    composed_image_path,
    ensure_output_dirs,
    script_path,
    section_audio_path,
    section_image_path,
)


def test_section_image_path_zero_pads_both_numbers():
    assert section_image_path(1, 3).name == "section_01_shot_03.png"
    assert section_image_path(12, 10).name == "section_12_shot_10.png"


def test_section_audio_path_is_one_file_per_section():
    assert section_audio_path(2).name == "section_02.mp3"


def test_composed_image_path_is_prefixed_and_separate():
    path = composed_image_path(1, 2)
    assert path.name == "composed_section_01_shot_02.png"
    assert path.parent == COMPOSED_IMAGE_OUTPUT_DIR


def test_script_path_is_named_script_json():
    assert script_path().name == "script.json"


def test_ensure_output_dirs_creates_the_composed_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    assert (tmp_path / COMPOSED_IMAGE_OUTPUT_DIR).is_dir()
