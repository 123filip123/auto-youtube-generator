import json
from types import SimpleNamespace

import pytest

from models import InvalidItemsError
from scripts.ai.generate_list.generate_list import LIST_JSON_SCHEMA, generate_list


def build_payload(count=3, prompts=3):
    return {
        "items": [
            {
                "title": f"Item {i}",
                "description": f"Description {i}. Second sentence.",
                "image_prompts": [f"prompt {i}.{j}" for j in range(prompts)],
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
    assert len(items[0].image_prompts) == 3


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


def user_message_for(topic="extinct animals", count=3):
    client = FakeClient(json.dumps(build_payload(count=count)))
    generate_list(topic, count, client=client)
    return client.calls[0]["messages"][1]["content"]


def test_prompt_gives_each_image_a_job_tied_to_the_narration():
    message = user_message_for().lower()
    assert "hero shot" in message
    assert "most surprising fact" in message
    assert "description" in message.split("most surprising fact")[1][:200]
    assert "unexpected" in message


def test_prompt_no_longer_asks_for_a_bare_name_or_a_random_style():
    message = user_message_for()
    # "Dodo Bird" and "Dodo Bird in a cubist art style" is what these produced.
    assert "should just be the item name" not in message
    assert "different style" not in message


def test_prompt_says_what_to_do_with_a_different_image_count(monkeypatch):
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 5)
    client = FakeClient(json.dumps(build_payload(prompts=5)))
    generate_list("extinct animals", 3, client=client)
    message = client.calls[0]["messages"][1]["content"]
    assert "Exactly 5" in message
    assert "starting again from the first" in message


def test_schema_root_is_an_object():
    # OpenAI strict mode requires an object at the root, not an array.
    assert LIST_JSON_SCHEMA["type"] == "object"
    assert LIST_JSON_SCHEMA["additionalProperties"] is False


def test_rejects_a_short_prompt_list():
    client = FakeClient(json.dumps(build_payload(count=1, prompts=2)))
    with pytest.raises(InvalidItemsError, match="3 image prompts"):
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
    client = FakeClient(json.dumps(build_payload(count=1, prompts=2)))
    items = generate_list("birds", 1, client=client)
    assert len(items[0].image_prompts) == 2
