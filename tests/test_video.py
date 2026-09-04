from pathlib import Path

import pytest
from PIL import Image

import config
from models import Beat, Item
from scripts.non_ai.generate_video_short.utils import (
    beat_weights,
    segment_bounds,
    zoom_scale,
)


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

    items = [Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in range(1, 4):
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


def test_segment_bounds_accepts_equal_weights_like_a_count():
    assert segment_bounds(9.0, [1, 1, 1]) == segment_bounds(9.0, 3)


def test_segment_bounds_splits_proportionally_to_the_weights():
    bounds = segment_bounds(10.0, [1, 4])
    assert bounds[0] == (0.0, pytest.approx(2.0))
    assert bounds[1] == (pytest.approx(2.0), pytest.approx(8.0))


def test_segment_bounds_still_covers_the_whole_duration_when_weighted():
    start, duration = segment_bounds(10.0, [3, 1, 5, 2])[-1]
    assert start + duration == pytest.approx(10.0)


def test_segment_bounds_falls_back_to_equal_when_every_weight_is_zero():
    # Archives written before storyboards have no narration to weigh.
    assert segment_bounds(9.0, [0, 0, 0]) == segment_bounds(9.0, 3)


def test_segment_bounds_rejects_no_weights():
    with pytest.raises(ValueError):
        segment_bounds(5.0, [])


def test_beat_weights_counts_narration_words():
    item = Item("T", "d", (Beat("one two three", "p1"), Beat("four", "p2")))
    assert beat_weights(item) == [3.0, 1.0]


def test_beat_weights_are_all_zero_for_legacy_items():
    assert beat_weights(Item.from_prompts("T", "d", ("a", "b"))) == [0.0, 0.0]
