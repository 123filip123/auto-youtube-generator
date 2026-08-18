"""Single-item narration against the OpenAI speech API."""

import os
from pathlib import Path

import config
from models import Item
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


@with_retry
def generate_audio_for_item(item: Item, destination: Path, *, client=None) -> Path:
    """Narrate one item's title and description into `destination`."""
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.audio.speech.create(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        instructions=config.TTS_INSTRUCTIONS,
        input=item.narration,
    )

    payload = b"".join(response.iter_bytes())
    if not payload:
        raise ValueError(f"No audio data returned from API for item: {item.title!r}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)

    return destination
