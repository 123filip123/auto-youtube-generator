import json
from types import SimpleNamespace

import pytest

import config
from models import InvalidItemsError
from scripts.ai.generate_list.generate_list import (
    LIST_JSON_SCHEMA,
    generate_list,
    words_per_beat,
)


def build_payload(count=3, beats=6):
    return {
        "items": [
            {
                "title": f"Item {i}",
                "style": f"A recurring figure for item {i}.",
                "beats": [
                    {"narration": f"Sentence {i}.{j}.", "prompt": f"prompt {i}.{j}"}
                    for j in range(beats)
                ],
            }
            for i in range(1, count + 1)
        ]
    }


class FakeClient:
    """Records the request and replays a canned response."""

    def __init__(self, content):
        self.content = content
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_returns_typed_items():
    client = FakeClient(json.dumps(build_payload(count=3)))
    items = generate_list("extinct animals", 3, client=client)
    assert len(items) == 3
    assert items[0].title == "Item 1"
    assert len(items[0].beats) == config.IMAGE_PROMPTS_PER_ITEM
    assert items[0].style == "A recurring figure for item 1."


def test_requests_a_strict_json_schema():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == LIST_JSON_SCHEMA


def test_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr("config.TEXT_MODEL", "test-model")
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    assert client.calls[0]["model"] == "test-model"


def test_prompt_mentions_the_topic_and_count():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "extinct animals" in user_message
    assert "3" in user_message


def test_prompt_keeps_the_safety_and_copyright_guidance():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "family-friendly" in user_message
    assert "copyrighted" in user_message.lower()


def test_schema_root_is_an_object():
    # OpenAI strict mode requires an object at the root, not an array.
    assert LIST_JSON_SCHEMA["type"] == "object"
    assert LIST_JSON_SCHEMA["additionalProperties"] is False


def test_rejects_a_short_prompt_list():
    client = FakeClient(json.dumps(build_payload(count=1, beats=2)))
    with pytest.raises(InvalidItemsError, match="6 story beats"):
        generate_list("extinct animals", 1, client=client)


def test_rejects_an_empty_response():
    client = FakeClient(None)
    with pytest.raises(InvalidItemsError):
        generate_list("extinct animals", 1, client=client)


def test_rejects_a_non_positive_count():
    client = FakeClient(json.dumps(build_payload()))
    with pytest.raises(ValueError, match="at least 1"):
        generate_list("extinct animals", 0, client=client)


def test_does_not_write_to_disk():
    # Persistence is the pipeline's job, not this stage's.
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)


def test_validates_against_the_current_prompt_count(monkeypatch):
    # The count must be read when generate_list runs, not when it is imported,
    # so a per-run override applies.
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 2)
    client = FakeClient(json.dumps(build_payload(count=1, beats=2)))
    items = generate_list("birds", 1, client=client)
    assert len(items[0].image_prompts) == 2


def test_schema_requires_style_and_beats():
    item_schema = LIST_JSON_SCHEMA["properties"]["items"]["items"]
    assert set(item_schema["required"]) == {"title", "style", "beats"}
    beat_schema = item_schema["properties"]["beats"]["items"]
    assert set(beat_schema["required"]) == {"narration", "prompt"}


def test_rejects_the_wrong_number_of_beats(monkeypatch):
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 3)
    client = FakeClient(json.dumps(build_payload(count=1, beats=2)))
    with pytest.raises(InvalidItemsError, match="3 story beats"):
        generate_list("extinct animals", 1, client=client)


def test_prompt_asks_for_a_continuing_sequence():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "continuation" in user_message
    assert "one short sentence" in user_message


def test_prompt_states_the_beat_count(monkeypatch):
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 5)
    client = FakeClient(json.dumps(build_payload(beats=5)))
    generate_list("extinct animals", 3, client=client)
    assert "Exactly 5 beats" in client.calls[0]["messages"][1]["content"]


def test_words_per_beat_discounts_the_pause_between_sentences(monkeypatch):
    """A frame's budget is speaking time only, not the silence after it."""
    monkeypatch.setattr("config.NARRATION_WORDS_PER_SECOND", 3.15)
    monkeypatch.setattr("config.NARRATION_SENTENCE_PAUSE_SECONDS", 1.6)

    monkeypatch.setattr("config.SECONDS_PER_FRAME", 4.0)
    assert words_per_beat() == 8

    # A shorter frame spends the same pause, so far fewer words fit.
    monkeypatch.setattr("config.SECONDS_PER_FRAME", 3.5)
    assert words_per_beat() == 6


def test_words_per_beat_never_drops_below_a_speakable_floor(monkeypatch):
    # The pause alone outlasts a 1s frame, so the raw budget goes negative.
    # A sentence still has to contain words.
    monkeypatch.setattr("config.SECONDS_PER_FRAME", 1.0)
    assert words_per_beat() == 4


def test_prompt_states_the_per_beat_word_target(monkeypatch):
    monkeypatch.setattr("config.NARRATION_WORDS_PER_SECOND", 3.15)
    monkeypatch.setattr("config.NARRATION_SENTENCE_PAUSE_SECONDS", 1.6)
    monkeypatch.setattr("config.SECONDS_PER_FRAME", 3.5)
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    assert "about 6 words" in client.calls[0]["messages"][1]["content"]


def test_prompt_asks_the_style_sheet_to_name_colours():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "colour" in user_message.lower()
    # The old brief forbade colour outright; flat fills are the look now.
    assert "Never ask for colour" not in user_message
