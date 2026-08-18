from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Item
from scripts.ai.generate_audios.generate_audio import audio_jobs, generate_audio_for_items
from scripts.ai.generate_audios.utils import generate_audio_for_item

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


def two_items():
    return [
        Item("Dodo", "A flightless bird.", ("a", "b", "c")),
        Item("Moa", "A very tall bird.", ("a", "b", "c")),
    ]


def test_writes_the_audio_bytes(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "item_01.mp3"
    assert generate_audio_for_item(two_items()[0], destination, client=client) == destination
    assert destination.read_bytes() == MP3_BYTES


def test_narrates_title_then_description(tmp_path):
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert speech.calls[0]["input"] == "Dodo. A flightless bird."


def test_uses_the_configured_tts_model_and_voice(tmp_path, monkeypatch):
    monkeypatch.setattr("config.TTS_MODEL", "test-tts")
    monkeypatch.setattr("config.TTS_VOICE", "coral")
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert speech.calls[0]["model"] == "test-tts"
    assert speech.calls[0]["voice"] == "coral"


def test_sends_the_voice_instructions(tmp_path):
    # The old code sent these to tts-1, which silently ignored them.
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert "conversational" in speech.calls[0]["instructions"]


def test_creates_parent_directories(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "deep" / "a.mp3"
    generate_audio_for_item(two_items()[0], destination, client=client)
    assert destination.exists()


def test_rejects_an_empty_response(tmp_path):
    client, _ = fake_client(payload=b"")
    with pytest.raises(ValueError, match="No audio data"):
        generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)


def test_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(payload=b"")
    destination = tmp_path / "a.mp3"
    with pytest.raises(ValueError):
        generate_audio_for_item(two_items()[0], destination, client=client)
    assert not destination.exists()


def test_audio_jobs_fans_out_one_job_per_item():
    client, _ = fake_client()
    jobs = audio_jobs(two_items(), client=client)
    assert len(jobs) == 2
    assert [label for label, _ in jobs] == ["audio item 1", "audio item 2"]


def test_audio_jobs_are_not_executed_when_built():
    client, speech = fake_client()
    audio_jobs(two_items(), client=client)
    assert speech.calls == []


def test_generate_audio_for_items_writes_every_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client()
    results = generate_audio_for_items(two_items(), client=client)
    assert all(r.ok for r in results)
    assert Path("outputs/audio_output/item_01.mp3").exists()
    assert Path("outputs/audio_output/item_02.mp3").exists()
