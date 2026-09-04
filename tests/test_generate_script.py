import json
from types import SimpleNamespace

import pytest

import config
from models import InvalidScriptError
from scripts.ai.generate_script.generate_script import (
    SCRIPT_JSON_SCHEMA,
    build_script_message,
    generate_script,
)
from utils.timing import word_budget


def build_payload(sections=4):
    return {
        "title": "Wolves Domesticated Themselves",
        "sections": [
            {"label": f"SECTION {i}", "narration": f"Narration number {i}."}
            for i in range(1, sections + 1)
        ],
    }


class FakeClient:
    """Records the request and replays a canned response."""

    def __init__(self, content):
        self.content = content
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_returns_a_typed_script_carrying_the_topic():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("how dogs evolved from wolves", 85, client=client)
    assert script.topic == "how dogs evolved from wolves"
    assert script.title == "Wolves Domesticated Themselves"
    assert len(script.sections) == 4
    assert script.sections[0].label == "SECTION 1"


def test_sections_have_no_prompts_yet():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("wolves", 85, client=client)
    assert all(section.prompts == () for section in script.sections)


def test_estimated_timings_are_filled_in():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("wolves", 85, client=client)
    assert script.sections[0].start == 0.0
    assert script.sections[-1].end > 0
    assert script.sections[1].start == pytest.approx(script.sections[0].end)


def test_requests_a_strict_json_schema():
    client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", 85, client=client)
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == SCRIPT_JSON_SCHEMA


def test_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr(config, "TEXT_MODEL", "test-model")
    client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", 85, client=client)
    assert client.calls[0]["model"] == "test-model"


def test_defaults_the_target_to_config():
    monkeypatchless_client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", client=monkeypatchless_client)
    sent = monkeypatchless_client.calls[0]["messages"][1]["content"]
    assert str(config.TARGET_VIDEO_SECONDS) in sent


def test_message_states_the_pause_corrected_word_budget():
    message = build_script_message("wolves", 85)
    assert str(word_budget(85)) in message
    # The naive figure would be 267; it must not appear.
    assert str(round(85 * config.NARRATION_WORDS_PER_SECOND)) not in message


def test_message_keeps_the_safety_and_copyright_guidance():
    message = build_script_message("wolves", 85)
    assert "family-friendly" in message
    assert "copyrighted" in message.lower()


def test_rejects_a_target_below_the_floor():
    with pytest.raises(ValueError, match="at least"):
        generate_script("wolves", 0, client=FakeClient("{}"))


def test_surfaces_a_malformed_response():
    client = FakeClient(json.dumps({"title": "T", "sections": []}))
    with pytest.raises(InvalidScriptError):
        generate_script("wolves", 85, client=client)
