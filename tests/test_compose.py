import pytest
from PIL import Image

import config
from models import Script, Section
from scripts.non_ai.compose_frames.compose_frames import compose_jobs
from scripts.non_ai.compose_frames.utils import (
    blurred_background,
    compose_frame,
    scaled_height,
)


def write_source(path, size=(1024, 1024), colour=(200, 30, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    return path


def build_script():
    return Script(
        topic="t",
        title="T",
        sections=(
            Section("HOOK", "N.", ("p1", "p2")),
            Section("SETUP", "N.", ("p1",)),
        ),
    )


def test_scaled_height_preserves_aspect_ratio():
    assert scaled_height(1000, 500, 1080) == 540


def test_scaled_height_rejects_a_degenerate_source():
    with pytest.raises(ValueError, match="non-positive"):
        scaled_height(0, 100, 1080)


def test_composed_frame_is_the_full_shorts_canvas(tmp_path):
    source = write_source(tmp_path / "in.png")
    destination = compose_frame(source, tmp_path / "out.png")
    with Image.open(destination) as composed:
        assert composed.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_image_is_centred_vertically(tmp_path):
    """A square source on a 9:16 canvas leaves equal bands above and below."""
    source = write_source(tmp_path / "in.png", size=(1024, 1024))
    destination = compose_frame(source, tmp_path / "out.png")
    foreground_height = scaled_height(1024, 1024, config.VIDEO_WIDTH)
    expected_top = (config.VIDEO_HEIGHT - foreground_height) // 2
    with Image.open(destination) as composed:
        pixels = composed.convert("RGB")
        # The source colour starts at the top of the centred foreground.
        assert pixels.getpixel((config.VIDEO_WIDTH // 2, expected_top + 5)) == (200, 30, 30)
        # And the band above it is backdrop, not source.
        assert pixels.getpixel((config.VIDEO_WIDTH // 2, expected_top - 20)) != (200, 30, 30)


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Source image not found"):
        compose_frame(tmp_path / "absent.png", tmp_path / "out.png")


def test_blurred_background_fills_the_canvas(tmp_path):
    with Image.open(write_source(tmp_path / "in.png")) as source:
        background = blurred_background(source, (config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
    assert background.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_one_job_per_shot_across_every_section():
    labels = [label for label, _ in compose_jobs(build_script())]
    assert labels == [
        "compose section 1 shot 1",
        "compose section 1 shot 2",
        "compose section 2 shot 1",
    ]


def test_composition_uses_no_font(tmp_path, monkeypatch):
    """Regression guard: the title path is gone, so no font is ever loaded."""
    import PIL.ImageFont

    def explode(*args, **kwargs):
        raise AssertionError("compose_frame must not load a font")

    monkeypatch.setattr(PIL.ImageFont, "truetype", explode)
    source = write_source(tmp_path / "in.png")
    compose_frame(source, tmp_path / "out.png")
