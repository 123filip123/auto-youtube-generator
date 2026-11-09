"""Compose a source image and its title into a 1080x1920 Shorts frame."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config


class TitleFontNotFoundError(RuntimeError):
    """No usable TrueType font was found on this machine."""


# Absolute paths first (reliable), then bare names for PIL's own font search.
# Falling back to ImageFont.load_default() is deliberately NOT an option: it
# silently renders titles at ~10px, which is how this broke on Linux.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "Arial Bold.ttf",
    "Arial.ttf",
    "arial.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
)


@lru_cache(maxsize=8)
def load_title_font(size: int) -> ImageFont.FreeTypeFont:
    """Find a usable TrueType font, or fail loudly.

    Cached, because this used to be re-resolved once per titled image.
    """
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    raise TitleFontNotFoundError(
        "No usable TrueType font found. Tried:\n  "
        + "\n  ".join(FONT_CANDIDATES)
        + "\nInstall one (on Debian/Ubuntu: apt install fonts-dejavu-core) or add "
        "a path to FONT_CANDIDATES."
    )


def scaled_height(source_width: int, source_height: int, target_width: int) -> int:
    """Height that preserves the aspect ratio when scaling to `target_width`."""
    if source_height <= 0 or source_width <= 0:
        raise ValueError(
            f"Source image has a non-positive dimension: "
            f"{source_width}x{source_height}"
        )
    return round(target_width * source_height / source_width)


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """Greedily wrap `text` to lines no wider than `max_width` pixels."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        elif current:
            lines.append(" ".join(current))
            current = [word]
        else:
            # A single word wider than the line; emit it and move on.
            lines.append(word)
            current = []

    if current:
        lines.append(" ".join(current))
    return lines


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

    overlay = Image.new(
        "RGBA", size, (255, 255, 255, config.BACKGROUND_OVERLAY_ALPHA)
    )
    return Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")


def create_titled_image_short(
    source_path: Path, title: str, destination: Path
) -> Path:
    """Render `source_path` onto a blurred backdrop with `title` beneath it."""
    source_path = Path(source_path)
    destination = Path(destination)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)

    canvas_size = (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)

    # Opened once and reused for both foreground and background; the previous
    # version opened the same file twice.
    with Image.open(source_path) as opened:
        source = opened.convert("RGB")

        foreground_height = scaled_height(
            source.width, source.height, config.VIDEO_WIDTH
        )
        foreground = source.resize(
            (config.VIDEO_WIDTH, foreground_height), Image.Resampling.LANCZOS
        )
        canvas = blurred_background(source, canvas_size)

    foreground_top = _foreground_top(foreground_height)
    canvas.paste(foreground, (0, foreground_top))
    _draw_title(canvas, title, foreground_top + foreground_height)

    canvas.save(destination)
    return destination


def _foreground_top(foreground_height: int) -> int:
    return (config.VIDEO_HEIGHT - foreground_height - 80) // 2


def _draw_title(canvas: Image.Image, title: str, image_bottom: int) -> None:
    """Draw `title`, wrapped and centred, below an image ending at `image_bottom`."""
    font = load_title_font(config.TITLE_FONT_SIZE)
    max_text_width = config.VIDEO_WIDTH - (2 * config.TITLE_SIDE_MARGIN)
    lines = wrap_text(title, font, max_text_width)
    if not lines:
        return

    draw = ImageDraw.Draw(canvas)
    line_height = config.TITLE_FONT_SIZE + config.TITLE_LINE_SPACING
    block_height = len(lines) * line_height
    block_top = image_bottom + config.TITLE_GAP_BELOW_IMAGE
    for index, line in enumerate(lines):
        y = block_top + (index * line_height) - (block_height // 2)
        draw.text(
            (config.VIDEO_WIDTH // 2, y),
            line,
            fill=config.TITLE_COLOR,
            font=font,
            anchor="mm",
        )


PLACEHOLDER_BACKGROUND = (235, 235, 235)
PLACEHOLDER_PANEL = (200, 200, 200)
PLACEHOLDER_MARK = (120, 120, 120)


def create_placeholder_titled_image(title: str, destination: Path) -> Path:
    """A frame for an item with no images: a large question mark and the title.

    Laid out like a normal frame, with a square panel where a square image
    would sit, so the title lands in the same place.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGB", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
                       PLACEHOLDER_BACKGROUND)
    panel_size = config.VIDEO_WIDTH
    panel_top = _foreground_top(panel_size)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        (0, panel_top, config.VIDEO_WIDTH, panel_top + panel_size),
        fill=PLACEHOLDER_PANEL,
    )
    mark_font = load_title_font(panel_size // 2)
    draw.text(
        (config.VIDEO_WIDTH // 2, panel_top + panel_size // 2),
        "?",
        fill=PLACEHOLDER_MARK,
        font=mark_font,
        anchor="mm",
    )
    _draw_title(canvas, title, panel_top + panel_size)

    canvas.save(destination)
    return destination
