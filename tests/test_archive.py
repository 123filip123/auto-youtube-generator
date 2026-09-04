import json
from pathlib import Path

import pytest

from models import Script, Section, load_script
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_script_to_generated_data,
)
from utils.paths import (
    ARCHIVED_SCRIPT_FILENAME,
    COMPOSED_IMAGE_OUTPUT_DIR,
    GENERATED_DATA_ROOT,
    ensure_output_dirs,
)


@pytest.fixture
def populated_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    Path("outputs/audio_output/item_01.mp3").write_bytes(b"audio")
    Path("outputs/image_output/item_01_prompt_01.png").write_bytes(b"image")
    Path("outputs/video_output/final_video_short.mp4").write_bytes(b"video")
    return tmp_path


def build_script(topic="how dogs evolved"):
    return Script(
        topic=topic,
        title="Wolves Domesticated Themselves",
        style="A grey-blue wolf.",
        sections=(
            Section("HOOK", "One line.", ("p1", "p2")),
            Section("SETUP", "Another line.", ("p1",)),
        ),
    )


def test_archives_under_the_topic_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    assert folder == GENERATED_DATA_ROOT / "how_dogs_evolved"
    assert (folder / ARCHIVED_SCRIPT_FILENAME).is_file()


def test_writes_measured_timings_over_the_estimates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    archived = load_script(folder / ARCHIVED_SCRIPT_FILENAME)
    assert (archived.sections[0].start, archived.sections[0].end) == (0.0, 4.0)
    assert (archived.sections[1].start, archived.sections[1].end) == (4.0, 10.0)


def test_copies_composed_frames_not_titled_ones(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    COMPOSED_IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_01_shot_01.png").write_bytes(b"png")
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    assert (folder / "composed_images" / "composed_section_01_shot_01.png").is_file()


def test_falls_back_to_a_timestamp_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(topic="!!!"), [4.0, 6.0])
    assert folder.name != "untitled"
    assert folder.name.isdigit() or "_" in folder.name


def test_mismatched_durations_raise_and_leave_no_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = build_script()  # 2 sections
    with pytest.raises(ValueError):
        save_script_to_generated_data(script, [4.0, 6.0, 8.0])  # 3 durations
    # Verify no archive directory was created
    assert not (GENERATED_DATA_ROOT / "how_dogs_evolved").exists()


def test_rearchiving_clears_stale_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()

    # First run with 4 sections
    COMPOSED_IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_01_shot_01.png").write_bytes(b"1")
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_02_shot_01.png").write_bytes(b"2")
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_03_shot_01.png").write_bytes(b"3")
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_04_shot_01.png").write_bytes(b"4")

    script1 = Script(
        topic="test",
        title="Test",
        style="A style",
        sections=tuple(
            Section(f"SECTION{i}", f"Line {i}", ("p1",))
            for i in range(1, 5)  # 4 sections
        ),
    )
    folder = save_script_to_generated_data(script1, [1.0, 2.0, 3.0, 4.0])
    assert (folder / "composed_images" / "composed_section_03_shot_01.png").exists()

    # Second run with 2 sections for same topic
    # Clear the output dir and add only 2 files
    for f in COMPOSED_IMAGE_OUTPUT_DIR.glob("*"):
        f.unlink()
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_01_shot_01.png").write_bytes(b"1b")
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_02_shot_01.png").write_bytes(b"2b")

    script2 = Script(
        topic="test",
        title="Test",
        style="A style",
        sections=tuple(
            Section(f"SECTION{i}", f"Line {i}", ("p1",))
            for i in range(1, 3)  # 2 sections
        ),
    )
    folder = save_script_to_generated_data(script2, [5.0, 6.0])

    # Verify stale files are gone
    assert not (folder / "composed_images" / "composed_section_03_shot_01.png").exists()
    assert not (folder / "composed_images" / "composed_section_04_shot_01.png").exists()
    # Verify new files exist
    assert (folder / "composed_images" / "composed_section_01_shot_01.png").exists()
    assert (folder / "composed_images" / "composed_section_02_shot_01.png").exists()
