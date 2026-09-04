from types import SimpleNamespace

import pytest
from PIL import Image

import config
from scripts.non_ai.generate_video_short.utils import segment_bounds


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
    from scripts.non_ai.generate_video_short.generate_video_short import (
        generate_video_from_script,
    )
    from utils.paths import composed_image_path, ensure_output_dirs, section_audio_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "VIDEO_WIDTH", 108)
    monkeypatch.setattr(config, "VIDEO_HEIGHT", 192)
    monkeypatch.setattr(config, "VIDEO_FPS", 6)
    ensure_output_dirs()

    script = Script(
        topic="dodo",
        title="Dodo",
        sections=(Section("HOOK", "A bird.", ("a", "b", "c")),),
    )
    for shot_number in range(1, 4):
        Image.new("RGB", (108, 192), (20, 40, 60)).save(
            composed_image_path(1, shot_number)
        )

    # A one-second silent mp3 generated with ffmpeg (bundled with imageio-ffmpeg).
    import subprocess

    import imageio_ffmpeg

    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
            str(section_audio_path(1)),
        ],
        check=True,
        capture_output=True,
    )

    output, durations = generate_video_from_script(script)
    assert output.exists()
    assert output.stat().st_size > 0
    assert len(durations) == 1


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


from models import Script, Section
from scripts.non_ai.generate_video_short import utils as video_utils
from scripts.non_ai.generate_video_short.utils import segment_bounds


def test_segment_bounds_splits_a_section_evenly():
    bounds = segment_bounds(10.0, 4)
    assert [round(duration, 6) for _, duration in bounds] == [2.5, 2.5, 2.5, 2.5]
    assert bounds[0][0] == 0.0
    assert round(bounds[-1][0], 6) == 7.5


def test_segment_bounds_rejects_a_section_with_no_shots():
    with pytest.raises(ValueError, match="at least one image"):
        segment_bounds(10.0, 0)


class FakeVoice:
    """Stands in for an AudioFileClip with a known duration."""

    def __init__(self, duration):
        self.duration = duration

    def set_start(self, start):
        self.start = start
        return self


def test_only_the_first_section_gets_intro_silence(monkeypatch):
    monkeypatch.setattr(video_utils, "AudioFileClip", lambda path: FakeVoice(10.0))
    monkeypatch.setattr(
        video_utils,
        "CompositeAudioClip",
        lambda clips: SimpleNamespace(set_duration=lambda d: SimpleNamespace(duration=d)),
    )

    _, first = video_utils.build_section_audio(1, is_first=True, is_last=False)
    _, middle = video_utils.build_section_audio(2, is_first=False, is_last=False)
    _, last = video_utils.build_section_audio(3, is_first=False, is_last=True)

    assert first == 10.0 + config.INTRO_SILENCE_SECONDS
    assert middle == 10.0
    assert last == 10.0 + config.OUTRO_SILENCE_SECONDS


def test_a_single_section_gets_both_silences(monkeypatch):
    monkeypatch.setattr(video_utils, "AudioFileClip", lambda path: FakeVoice(10.0))
    monkeypatch.setattr(
        video_utils,
        "CompositeAudioClip",
        lambda clips: SimpleNamespace(set_duration=lambda d: SimpleNamespace(duration=d)),
    )
    _, total = video_utils.build_section_audio(1, is_first=True, is_last=True)
    assert total == (
        10.0 + config.INTRO_SILENCE_SECONDS + config.OUTRO_SILENCE_SECONDS
    )
