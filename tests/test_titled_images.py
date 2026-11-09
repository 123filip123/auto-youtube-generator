from pathlib import Path

import pytest
from PIL import Image, ImageFont

import config
from models import Item
from scripts.non_ai.create_titled_images_short.create_titled_images_short import (
    create_titled_images_for_items_short,
)
from scripts.non_ai.create_titled_images_short.utils import (
    blurred_background,
    create_placeholder_titled_image,
    create_titled_image_short,
    load_title_font,
    scaled_height,
    wrap_text,
)


@pytest.fixture
def square_image(tmp_path):
    path = tmp_path / "src.png"
    Image.new("RGB", (1024, 1024), (30, 90, 150)).save(path)
    return path


@pytest.fixture
def wide_image(tmp_path):
    path = tmp_path / "wide.png"
    Image.new("RGB", (1600, 900), (30, 90, 150)).save(path)
    return path


def test_scaled_height_preserves_a_square():
    assert scaled_height(1024, 1024, 1080) == 1080


def test_scaled_height_preserves_a_landscape_ratio():
    # The old code multiplied by the aspect ratio, producing 1920 here.
    assert scaled_height(1600, 900, 1080) == 608


def test_scaled_height_preserves_a_portrait_ratio():
    assert scaled_height(900, 1600, 1080) == 1920


def test_scaled_height_rejects_zero_height():
    with pytest.raises(ValueError):
        scaled_height(1024, 0, 1080)


def test_load_title_font_returns_a_real_truetype_font():
    font = load_title_font(120)
    assert isinstance(font, ImageFont.FreeTypeFont)
    # A silent fallback to load_default() would give a ~10px bitmap font.
    assert font.getbbox("Hg")[3] > 50


def test_load_title_font_is_cached():
    assert load_title_font(120) is load_title_font(120)


def test_wrap_text_keeps_short_text_on_one_line():
    font = load_title_font(120)
    assert wrap_text("Dodo", font, 980) == ["Dodo"]


def test_wrap_text_splits_long_text():
    font = load_title_font(120)
    lines = wrap_text("The Extraordinarily Long Extinct Bird Name", font, 980)
    assert len(lines) > 1
    assert " ".join(lines) == "The Extraordinarily Long Extinct Bird Name"


def test_wrap_text_emits_an_oversized_word_on_its_own_line():
    font = load_title_font(120)
    lines = wrap_text("Supercalifragilisticexpialidocious", font, 200)
    assert lines == ["Supercalifragilisticexpialidocious"]


def test_wrap_text_handles_empty_input():
    font = load_title_font(120)
    assert wrap_text("", font, 980) == []


def test_blurred_background_returns_the_requested_size(square_image):
    source = Image.open(square_image)
    result = blurred_background(source, (1080, 1920))
    assert result.size == (1080, 1920)
    assert result.mode == "RGB"


def test_blurred_background_actually_blurs(square_image):
    source = Image.new("RGB", (200, 200))
    for x in range(200):
        for y in range(200):
            source.putpixel((x, y), (255, 0, 0) if (x // 10) % 2 else (0, 0, 255))
    result = blurred_background(source, (100, 100))
    # Hard red/blue stripes must average into intermediate colours.
    colours = {result.getpixel((x, 50)) for x in range(10, 90)}
    assert not colours <= {(255, 0, 0), (0, 0, 255)}


def test_create_titled_image_writes_correct_dimensions(square_image, tmp_path):
    destination = tmp_path / "out.png"
    create_titled_image_short(square_image, "Dodo", destination)
    with Image.open(destination) as result:
        assert result.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_create_titled_image_handles_a_non_square_source(wide_image, tmp_path):
    # The aspect-ratio bug made this produce a 1080x1920 foreground that
    # completely covered the background.
    destination = tmp_path / "out.png"
    create_titled_image_short(wide_image, "Wide", destination)
    with Image.open(destination) as result:
        assert result.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_create_titled_image_creates_parent_directories(square_image, tmp_path):
    destination = tmp_path / "deep" / "out.png"
    create_titled_image_short(square_image, "Dodo", destination)
    assert destination.exists()


def test_create_titled_image_raises_on_a_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_titled_image_short(tmp_path / "nope.png", "X", tmp_path / "out.png")


def test_batch_renders_every_item_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("outputs/image_output").mkdir(parents=True)
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in range(1, 4):
        Image.new("RGB", (1024, 1024), (10, 20, 30)).save(
            Path(f"outputs/image_output/item_01_prompt_{prompt_number:02d}.png")
        )

    results = create_titled_images_for_items_short(items)

    assert all(r.ok for r in results)
    assert Path("outputs/titled_image_output/item_01_prompt_01_short.png").exists()
    assert Path("outputs/titled_image_output/item_01_prompt_03_short.png").exists()


def test_batch_renders_only_the_images_an_item_has(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("outputs/image_output").mkdir(parents=True)
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in (1, 3):
        Image.new("RGB", (1024, 1024)).save(
            Path(f"outputs/image_output/item_01_prompt_{prompt_number:02d}.png")
        )

    results = create_titled_images_for_items_short(items)

    assert len(results) == 2 and all(r.ok for r in results)
    assert Path("outputs/titled_image_output/item_01_prompt_01_short.png").exists()
    assert not Path("outputs/titled_image_output/item_01_prompt_02_short.png").exists()
    assert Path("outputs/titled_image_output/item_01_prompt_03_short.png").exists()


def test_batch_renders_a_placeholder_for_an_item_with_no_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("outputs/image_output").mkdir(parents=True)
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]

    results = create_titled_images_for_items_short(items)

    assert len(results) == 1 and results[0].ok
    with Image.open("outputs/titled_image_output/item_01_prompt_01_short.png") as frame:
        assert frame.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_placeholder_draws_a_question_mark_in_the_image_area(tmp_path):
    destination = tmp_path / "placeholder.png"
    create_placeholder_titled_image("Dodo", destination)
    with Image.open(destination) as frame:
        background = frame.getpixel((5, 5))
        image_area = frame.crop(
            (0, config.VIDEO_HEIGHT // 4, config.VIDEO_WIDTH, config.VIDEO_HEIGHT // 2)
        )
        colours = {colour for _, colour in image_area.getcolors(maxcolors=1 << 16)}
    assert colours - {background}, "nothing was drawn where the image would be"
