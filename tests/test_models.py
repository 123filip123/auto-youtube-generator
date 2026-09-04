import json

import pytest

from models import (
    InvalidScriptError,
    Script,
    Section,
    load_script,
    parse_script,
    save_script,
    with_durations,
    with_estimated_timings,
)


def build_script_payload(sections=2, prompts=2):
    return {
        "title": "Wolves Domesticated Themselves",
        "sections": [
            {
                "label": f"SECTION {i}",
                "narration": f"Narration for section {i}.",
                "prompts": [f"prompt {i}.{j}" for j in range(prompts)],
            }
            for i in range(1, sections + 1)
        ],
    }


def test_parse_script_reads_sections_and_prompts():
    script = parse_script(json.dumps(build_script_payload()), topic="wolves")
    assert script.topic == "wolves"
    assert script.title == "Wolves Domesticated Themselves"
    assert len(script.sections) == 2
    assert script.sections[0].label == "SECTION 1"
    assert script.sections[0].prompts == ("prompt 1.0", "prompt 1.1")


def test_parse_script_allows_sections_without_prompts():
    payload = build_script_payload()
    for section in payload["sections"]:
        del section["prompts"]
    script = parse_script(payload, topic="wolves")
    assert script.sections[0].prompts == ()


def test_parse_script_rejects_an_empty_section_list():
    with pytest.raises(InvalidScriptError, match="at least one section"):
        parse_script({"title": "T", "sections": []})


def test_parse_script_rejects_a_blank_narration():
    payload = build_script_payload()
    payload["sections"][0]["narration"] = "   "
    with pytest.raises(InvalidScriptError, match="narration"):
        parse_script(payload)


def test_parse_script_rejects_a_blank_label():
    payload = build_script_payload()
    payload["sections"][1]["label"] = ""
    with pytest.raises(InvalidScriptError, match="label"):
        parse_script(payload)


def test_parse_script_rejects_non_json():
    with pytest.raises(InvalidScriptError, match="valid JSON"):
        parse_script("not json at all")


def test_with_durations_lays_sections_end_to_end():
    script = parse_script(build_script_payload())
    timed = with_durations(script, [4.0, 6.0])
    assert (timed.sections[0].start, timed.sections[0].end) == (0.0, 4.0)
    assert (timed.sections[1].start, timed.sections[1].end) == (4.0, 10.0)


def test_with_durations_rejects_a_length_mismatch():
    script = parse_script(build_script_payload())
    with pytest.raises(ValueError, match="2 sections"):
        with_durations(script, [4.0])


def test_with_estimated_timings_uses_speaking_time():
    script = parse_script(build_script_payload())
    timed = with_estimated_timings(script)
    assert timed.sections[0].start == 0.0
    assert timed.sections[1].start == pytest.approx(timed.sections[0].end)
    assert timed.sections[-1].end > 0


def test_save_and_load_script_round_trips(tmp_path):
    script = with_estimated_timings(parse_script(build_script_payload(), topic="wolves"))
    destination = tmp_path / "script.json"
    save_script(script, destination)
    assert load_script(destination) == script


def test_saved_script_carries_topic_style_and_timings(tmp_path):
    script = Script(
        topic="wolves",
        title="T",
        style="A grey-blue wolf.",
        sections=(Section("HOOK", "One line.", ("p1",), 0.0, 3.0),),
    )
    destination = tmp_path / "script.json"
    save_script(script, destination)
    payload = json.loads(destination.read_text())
    assert payload["topic"] == "wolves"
    assert payload["style"] == "A grey-blue wolf."
    assert payload["sections"][0]["start"] == 0.0
    assert payload["sections"][0]["end"] == 3.0
