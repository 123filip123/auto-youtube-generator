"""Single-image generation against the OpenAI images API."""

import base64
import os
from pathlib import Path

import openai

import config
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry

REWRITE_SYSTEM_MESSAGE = (
    "You rewrite image generation prompts that an image model's safety system "
    "rejected. Keep the subject and what the image is meant to show, but "
    "remove whatever likely caused the rejection. Common causes are "
    "recreating a real artwork, album cover, poster, logo or photograph, "
    "depicting a real, identifiable person, or violent or adult content. "
    "Describe an original scene that evokes the same era, mood or idea "
    "instead. Reply with the new prompt only."
)


def _is_moderation_block(error: openai.BadRequestError) -> bool:
    return getattr(error, "code", None) == "moderation_blocked"


@with_retry
def _request_image(client, prompt: str) -> str:
    response = client.images.generate(
        model=config.IMAGE_MODEL,
        prompt=prompt,
        size=config.IMAGE_SIZE,
        n=1,
        quality=config.IMAGE_QUALITY,
    )
    if not response.data or not response.data[0] or not response.data[0].b64_json:
        raise ValueError(f"No image data returned from API for prompt: {prompt!r}")
    return response.data[0].b64_json


@with_retry
def _rewrite_blocked_prompt(client, prompt: str) -> str:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_MESSAGE},
            {"role": "user", "content": f"Rejected prompt: {prompt}"},
        ],
        temperature=config.TEXT_TEMPERATURE,
    )
    rewritten = (response.choices[0].message.content or "").strip()
    if not rewritten:
        raise ValueError(f"Model returned no rewrite for blocked prompt: {prompt!r}")
    return rewritten


def generate_image(prompt: str, destination: Path, *, client=None) -> Path:
    """Generate one image for `prompt` and save it to `destination`.

    If the image API's safety system blocks the prompt, the text model
    rewrites it once and the image is requested again. A second block raises.

    Writes through a temporary file and renames on success, so a failure can
    never leave a truncated PNG behind for the validation step to find.
    """
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        b64 = _request_image(client, prompt)
    except openai.BadRequestError as error:
        if not _is_moderation_block(error):
            raise
        b64 = _request_image(client, _rewrite_blocked_prompt(client, prompt))

    image_bytes = base64.b64decode(b64)

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(image_bytes)
    os.replace(temporary, destination)

    return destination
