"""Compose a source image onto a 1080x1920 Shorts frame.

No text. The narration carries the message, and a static title burned across
eighty-five seconds of continuous video reads as clutter.
"""

from pathlib import Path

from PIL import Image, ImageFilter

import config


def scaled_height(source_width: int, source_height: int, target_width: int) -> int:
    """Height that preserves the aspect ratio when scaling to `target_width`."""
    if source_height <= 0 or source_width <= 0:
        raise ValueError(
            f"Source image has a non-positive dimension: "
            f"{source_width}x{source_height}"
        )
    return round(target_width * source_height / source_width)


def blurred_background(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Build the blurred, lightened backdrop.

    Blurring at 1/N scale and upscaling gives a visually identical result to a
    full-resolution blur at this radius, for roughly 1/N^2 of the work.
    """
    width, height = size
    factor = config.BLUR_DOWNSCALE_FACTOR

    small_size = (max(1, width // factor), max(1, height // factor))
    small = source.convert("RGB").resize(small_size, Image.Resampling.BILINEAR)
    small = small.filter(
        ImageFilter.GaussianBlur(radius=config.BACKGROUND_BLUR_RADIUS / factor)
    )
    background = small.resize(size, Image.Resampling.BILINEAR)

    overlay = Image.new("RGBA", size, (255, 255, 255, config.BACKGROUND_OVERLAY_ALPHA))
    return Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")


def compose_frame(source_path: Path, destination: Path) -> Path:
    """Render `source_path` centred on its own blurred backdrop."""
    source_path = Path(source_path)
    destination = Path(destination)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas_size = (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)

    with Image.open(source_path) as opened:
        source = opened.convert("RGB")
        foreground_height = scaled_height(
            source.width, source.height, config.VIDEO_WIDTH
        )
        foreground = source.resize(
            (config.VIDEO_WIDTH, foreground_height), Image.Resampling.LANCZOS
        )
        canvas = blurred_background(source, canvas_size)

    # Centred, with no reserved band: nothing sits below the image any more.
    foreground_top = (config.VIDEO_HEIGHT - foreground_height) // 2
    canvas.paste(foreground, (0, foreground_top))

    canvas.save(destination)
    return destination
