from pathlib import Path

import pytest
from PIL import Image

import config
from models import Item
from scripts.non_ai.generate_video_short.utils import segment_bounds, zoom_scale
from utils.media import item_frame_paths
from utils.paths import ensure_output_dirs, image_path, titled_image_path


def test_item_frames_skip_images_that_failed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    for prompt_number in (1, 3):
        image_path(1, prompt_number).write_bytes(b"image")
    assert item_frame_paths(1, 3) == [titled_image_path(1, 1), titled_image_path(1, 3)]


def test_item_frames_fall_back_to_one_placeholder_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    assert item_frame_paths(1, 3) == [titled_image_path(1, 1)]


def test_zoom_starts_at_one():
    assert zoom_scale(0.0, 3.0, 1.2) == pytest.approx(1.0)


def test_zoom_reaches_the_end_scale():
    assert zoom_scale(3.0, 3.0, 1.2) == pytest.approx(1.2)


def test_zoom_is_linear_at_the_midpoint():
    assert zoom_scale(1.5, 3.0, 1.2) == pytest.approx(1.1)


def test_zoom_clamps_past_the_end():
    # moviepy can request t marginally beyond the clip duration.
    assert zoom_scale(3.5, 3.0, 1.2) == pytest.approx(1.2)


def test_zoom_clamps_before_the_start():
    assert zoom_scale(-1.0, 3.0, 1.2) == pytest.approx(1.0)


def test_zoom_handles_zero_duration():
    assert zoom_scale(0.0, 0.0, 1.2) == pytest.approx(1.0)


def test_segment_bounds_splits_evenly():
    bounds = segment_bounds(9.0, 3)
    assert bounds == [(0.0, 3.0), (3.0, 3.0), (6.0, 3.0)]


def test_segment_bounds_covers_the_whole_duration():
    bounds = segment_bounds(10.0, 3)
    start, duration = bounds[-1]
    assert start + duration == pytest.approx(10.0)


def test_segment_bounds_handles_a_single_image():
    assert segment_bounds(5.0, 1) == [(0.0, 5.0)]


def test_segment_bounds_handles_four_images():
    # The old code hardcoded range(1, 4) and could not do this.
    assert len(segment_bounds(8.0, 4)) == 4


def test_segment_bounds_rejects_zero_images():
    with pytest.raises(ValueError):
        segment_bounds(5.0, 0)


@pytest.mark.slow
def test_renders_a_real_video(tmp_path, monkeypatch):
    """End-to-end render with tiny assets. Deselect with -m 'not slow'."""
    from scripts.ai.generate_audios.utils import generate_audio_for_item  # noqa: F401
    from scripts.non_ai.generate_video_short.generate_video_short import (
        generate_video_short,
    )
    from utils.paths import audio_path, ensure_output_dirs, titled_image_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "VIDEO_WIDTH", 108)
    monkeypatch.setattr(config, "VIDEO_HEIGHT", 192)
    monkeypatch.setattr(config, "VIDEO_FPS", 6)
    ensure_output_dirs()

    # Prompt 2's image failed, so the item plays its other two.
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in (1, 3):
        image_path(1, prompt_number).write_bytes(b"image")
        Image.new("RGB", (108, 192), (20, 40, 60)).save(
            titled_image_path(1, prompt_number)
        )

    # A one-second silent mp3 generated with ffmpeg (bundled with imageio-ffmpeg).
    import subprocess

    import imageio_ffmpeg

    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
            str(audio_path(1)),
        ],
        check=True,
        capture_output=True,
    )

    output = generate_video_short(items)
    assert output.exists()
    assert output.stat().st_size > 0
