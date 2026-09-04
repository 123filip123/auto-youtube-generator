from types import SimpleNamespace

import pytest

MP3_BYTES = b"ID3\x03\x00\x00\x00fake mp3 payload"


class FakeSpeech:
    def __init__(self, payload=MP3_BYTES, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(iter_bytes=lambda: iter([self.payload]))


def fake_client(payload=MP3_BYTES, error=None):
    speech = FakeSpeech(payload=payload, error=error)
    return SimpleNamespace(audio=SimpleNamespace(speech=speech)), speech


from models import Script, Section
from scripts.ai.generate_audios.generate_audio import section_audio_jobs
from scripts.ai.generate_audios.utils import generate_audio_for_section


def build_script():
    return Script(
        topic="wolves",
        title="T",
        sections=(
            Section("HOOK", "Your dog's ancestor could have killed you."),
            Section("SETUP", "Grey wolves found our camps."),
        ),
    )


def test_narrates_the_section_text_only(tmp_path):
    """The label is a production note, not spoken words."""
    client, speech = fake_client()
    section = Section("HOOK", "Your dog's ancestor could have killed you.")
    generate_audio_for_section(section, tmp_path / "section_01.mp3", client=client)
    assert speech.calls[0]["input"] == "Your dog's ancestor could have killed you."
    assert "HOOK" not in speech.calls[0]["input"]


def test_writes_the_audio_file(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "section_01.mp3"
    generate_audio_for_section(Section("HOOK", "Line."), destination, client=client)
    assert destination.read_bytes() == MP3_BYTES


def test_raises_when_the_api_returns_nothing(tmp_path):
    client, _ = fake_client(payload=b"")
    with pytest.raises(ValueError, match="No audio data"):
        generate_audio_for_section(
            Section("HOOK", "Line."), tmp_path / "s.mp3", client=client
        )


def test_one_job_per_section_targeting_its_own_file():
    jobs = section_audio_jobs(build_script())
    assert [label for label, _ in jobs] == ["audio section 1", "audio section 2"]
