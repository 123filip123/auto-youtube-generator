"""Single-section narration against the OpenAI speech API."""

import os
from pathlib import Path

import config
from models import Section
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


@with_retry
def generate_audio_for_section(
    section: Section, destination: Path, *, client=None
) -> Path:
    """Narrate one section's prose into `destination`.

    The label is a production note, not spoken words — only `narration` is
    sent, which is also what makes the measured duration match the text the
    shots were counted from.
    """
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.audio.speech.create(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        instructions=config.TTS_INSTRUCTIONS,
        input=section.narration,
    )

    payload = b"".join(response.iter_bytes())
    if not payload:
        raise ValueError(
            f"No audio data returned from API for section: {section.label!r}"
        )

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)

    return destination
