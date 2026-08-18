"""Single-image generation against the OpenAI images API."""

import base64
import os
from pathlib import Path

import config
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


@with_retry
def generate_image(prompt: str, destination: Path, *, client=None) -> Path:
    """Generate one image for `prompt` and save it to `destination`.

    Writes through a temporary file and renames on success, so a failure can
    never leave a truncated PNG behind for the validation step to find.
    """
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

    if not response.data or not response.data[0] or not response.data[0].b64_json:
        raise ValueError(f"No image data returned from API for prompt: {prompt!r}")

    image_bytes = base64.b64decode(response.data[0].b64_json)

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(image_bytes)
    os.replace(temporary, destination)

    return destination
