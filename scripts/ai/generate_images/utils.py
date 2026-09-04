"""Single-image generation against the OpenAI images API."""

import base64
import os
from pathlib import Path

import config
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


def styled_prompt(item_style: str, prompt: str) -> str:
    """The global look, then the script's style sheet, then the beat itself."""
    parts = [config.STORYBOARD_STYLE, item_style.strip(), prompt.strip()]
    return " ".join(part for part in parts if part)


def _write_image(response, destination: Path, prompt: str) -> Path:
    """Decode one image response and write it atomically.

    Writes through a temporary file and renames on success, so a failure can
    never leave a truncated PNG behind for the validation step to find.
    """
    if not response.data or not response.data[0] or not response.data[0].b64_json:
        raise ValueError(f"No image data returned from API for prompt: {prompt!r}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(base64.b64decode(response.data[0].b64_json))
    os.replace(temporary, destination)

    return destination


@with_retry
def generate_image(prompt: str, destination: Path, *, client=None) -> Path:
    """Generate one image for `prompt` and save it to `destination`."""
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.images.generate(
        model=config.IMAGE_MODEL,
        prompt=prompt,
        size=config.IMAGE_SIZE,
        n=1,
        quality=config.IMAGE_QUALITY,
    )

    return _write_image(response, destination, prompt)


@with_retry
def generate_image_from_reference(
    prompt: str, reference: Path, destination: Path, *, client=None
) -> Path:
    """Draw `prompt` as a continuation of the already-generated `reference`.

    The reference is what keeps a character recognisable across a section's
    frames; a text style sheet alone lets the figure drift.
    """
    client = client or get_open_ai_client()
    reference = Path(reference)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not reference.is_file() or reference.stat().st_size == 0:
        raise FileNotFoundError(
            f"anchor frame is missing or empty, cannot continue from it: {reference}"
        )

    with reference.open("rb") as handle:
        response = client.images.edit(
            model=config.IMAGE_MODEL,
            image=[handle],
            prompt=prompt,
            size=config.IMAGE_SIZE,
            n=1,
            quality=config.IMAGE_QUALITY,
        )

    return _write_image(response, destination, prompt)
