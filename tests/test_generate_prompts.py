import json
from types import SimpleNamespace

import pytest

import config
from models import Script, Section
from scripts.ai.generate_prompts.generate_prompts import (
    PROMPTS_JSON_SCHEMA,
    PromptGenerationError,
    build_prompts_message,
    generate_prompts,
    shot_budgets,
)


def build_script():
    return Script(
        topic="wolves",
        title="Wolves Domesticated Themselves",
        sections=(
            Section("HOOK", "Your dog's ancestor could have killed you."),
            Section(
                "SETUP",
                "Grey wolves started hanging around human camps. "
                "Not because we tamed them. They chose the trash piles.",
            ),
        ),
    )


def build_response(counts, style="A lean grey-blue wolf with amber eyes."):
    return json.dumps(
        {
            "style": style,
            "sections": [
                {"label": f"S{i}", "prompts": [f"prompt {i}.{j}" for j in range(n)]}
                for i, n in enumerate(counts, start=1)
            ],
        }
    )


class FakeClient:
    """Replays a queue of canned responses, recording every request."""

    def __init__(self, *contents):
        self.contents = list(contents)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0) if self.contents else self.contents_last
        self.contents_last = content
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_shot_budgets_are_derived_per_section():
    budgets = shot_budgets(build_script())
    assert len(budgets) == 2
    assert all(count >= 1 for count in budgets)
    # The longer second section earns more shots than the one-line hook.
    assert budgets[1] > budgets[0]


def test_fills_style_and_prompts_onto_the_script():
    script = build_script()
    client = FakeClient(build_response([2, 4]))
    filled = generate_prompts(script, client=client)
    assert filled.style == "A lean grey-blue wolf with amber eyes."
    assert filled.sections[0].prompts == ("prompt 1.0", "prompt 1.1")
    assert len(filled.sections[1].prompts) == 4


def test_preserves_labels_narration_and_timings():
    script = build_script()
    filled = generate_prompts(script, client=FakeClient(build_response([2, 4])))
    for before, after in zip(script.sections, filled.sections):
        assert after.label == before.label
        assert after.narration == before.narration
        assert after.start == before.start


def test_merges_by_index_not_by_label():
    """Returned labels are ignored; position is the join key."""
    script = build_script()
    response = json.dumps(
        {
            "style": "A wolf.",
            "sections": [
                {"label": "TOTALLY WRONG", "prompts": ["a"]},
                {"label": "ALSO WRONG", "prompts": ["b", "c"]},
            ],
        }
    )
    filled = generate_prompts(script, client=FakeClient(response))
    assert filled.sections[0].label == "HOOK"
    assert filled.sections[0].prompts == ("a",)
    assert filled.sections[1].prompts == ("b", "c")


def test_an_off_budget_count_is_honoured_not_corrected():
    """A section returning fewer prompts than budgeted is accepted as-is."""
    script = build_script()
    budgets = shot_budgets(script)
    client = FakeClient(build_response([1, 1]))
    filled = generate_prompts(script, client=client)
    assert len(filled.sections[1].prompts) == 1
    assert budgets[1] != 1
    assert len(client.calls) == 1, "an off-budget count must not trigger a retry"


def test_an_empty_section_triggers_exactly_one_repair_call():
    script = build_script()
    client = FakeClient(build_response([2, 0]), build_response([2, 4]))
    filled = generate_prompts(script, client=client)
    assert len(client.calls) == 2
    assert len(filled.sections[1].prompts) == 4


def test_a_failed_repair_raises():
    script = build_script()
    client = FakeClient(build_response([2, 0]), build_response([2, 0]))
    with pytest.raises(PromptGenerationError, match="section 2"):
        generate_prompts(script, client=client)


def test_a_section_count_mismatch_triggers_a_repair():
    script = build_script()
    client = FakeClient(build_response([2]), build_response([2, 3]))
    filled = generate_prompts(script, client=client)
    assert len(client.calls) == 2
    assert len(filled.sections) == 2


def test_requests_a_strict_json_schema():
    generate_prompts(build_script(), client=(client := FakeClient(build_response([2, 4]))))
    response_format = client.calls[0]["response_format"]
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == PROMPTS_JSON_SCHEMA


def test_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr(config, "TEXT_MODEL", "test-model")
    client = FakeClient(build_response([2, 4]))
    generate_prompts(build_script(), client=client)
    assert client.calls[0]["model"] == "test-model"


def test_message_carries_every_narration_and_its_budget():
    script = build_script()
    message = build_prompts_message(script, shot_budgets(script))
    assert "Your dog's ancestor could have killed you." in message
    assert "HOOK" in message and "SETUP" in message
    assert "self-contained" in message


def test_message_explains_the_chain_and_the_reset():
    script = build_script()
    message = build_prompts_message(script, shot_budgets(script))
    assert "continuation" in message or "continues" in message
    assert "style sheet" in message.lower()
