import json

import pytest

from models import (
    Beat,
    InvalidItemsError,
    Item,
    InvalidScriptError,
    Script,
    Section,
    items_to_json,
    load_items,
    load_script,
    parse_items,
    parse_script,
    save_items,
    save_script,
    with_durations,
    with_estimated_timings,
)

def parse_any(raw):
    """Parse without the beat-count check; these tests are about shape."""
    return parse_items(raw, expected_prompts=None)


VALID_ITEM = {
    "title": "Dodo",
    "description": "A flightless bird. It lived on Mauritius.",
    "image_prompts": ["a dodo", "a dodo on a skateboard", "a dodo, watercolour"],
}


def test_parses_envelope_shape():
    items = parse_any(json.dumps({"items": [VALID_ITEM]}))
    assert len(items) == 1
    assert items[0].title == "Dodo"
    assert items[0].image_prompts == (
        "a dodo",
        "a dodo on a skateboard",
        "a dodo, watercolour",
    )


def test_parses_bare_list_shape():
    items = parse_any(json.dumps([VALID_ITEM]))
    assert len(items) == 1


def test_parses_already_decoded_python_objects():
    items = parse_any([VALID_ITEM])
    assert items[0].title == "Dodo"


def test_strips_markdown_fences_for_legacy_files():
    fenced = "```json\n" + json.dumps([VALID_ITEM]) + "\n```"
    assert len(parse_any(fenced)) == 1


def test_narration_joins_title_and_description():
    item = parse_any([VALID_ITEM])[0]
    assert item.narration == "Dodo. A flightless bird. It lived on Mauritius."


def test_item_is_immutable():
    item = parse_any([VALID_ITEM])[0]
    with pytest.raises(Exception):
        item.title = "changed"


def test_rejects_malformed_json():
    with pytest.raises(InvalidItemsError, match="not valid JSON"):
        parse_any("{oh no")


def test_rejects_empty_list():
    with pytest.raises(InvalidItemsError, match="no items"):
        parse_any("[]")


def test_rejects_missing_field():
    broken = {"title": "Dodo", "image_prompts": ["a", "b", "c"]}
    with pytest.raises(InvalidItemsError, match="item 1.*description"):
        parse_any([broken])


def test_rejects_blank_title():
    broken = dict(VALID_ITEM, title="   ")
    with pytest.raises(InvalidItemsError, match="item 1.*title"):
        parse_any([broken])


def test_rejects_wrong_prompt_count():
    broken = dict(VALID_ITEM, image_prompts=["only one"])
    with pytest.raises(InvalidItemsError, match="item 1.*3 story beats.*got 1"):
        parse_items([broken], expected_prompts=3)


def test_allows_any_prompt_count_when_expected_is_none():
    loose = dict(VALID_ITEM, image_prompts=["a", "b"])
    assert len(parse_items([loose], expected_prompts=None)[0].image_prompts) == 2


def test_reports_the_offending_index():
    with pytest.raises(InvalidItemsError, match="item 2"):
        parse_any([VALID_ITEM, {"title": "x"}])


def test_round_trips_through_disk(tmp_path):
    items = [Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))]
    target = tmp_path / "list.json"
    save_items(items, target)
    assert load_items(target) == items


def test_saved_json_uses_the_envelope_shape(tmp_path):
    target = tmp_path / "list.json"
    save_items([Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))], target)
    assert "items" in json.loads(target.read_text())


def test_save_creates_parent_directories(tmp_path):
    target = tmp_path / "deep" / "nested" / "list.json"
    save_items([Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))], target)
    assert target.exists()


def test_items_to_json_is_readable():
    text = items_to_json([Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))])
    assert "\n" in text  # indented, not one long line


def test_parse_items_rejects_an_empty_image_prompt_list():
    # all([]) is True, so an empty list used to slip through and then break
    # the renderer, which needs at least one image per item.
    payload = {
        "items": [{"title": "Dodo", "description": "A bird.", "image_prompts": []}]
    }
    with pytest.raises(InvalidItemsError, match="image_prompts"):
        parse_items(payload, expected_prompts=None)


STORYBOARD_ITEM = {
    "title": "Cavendish",
    "style": "A scientist with round glasses and a long coat.",
    "beats": [
        {"narration": "A scientist set out to weigh the world.",
         "prompt": "The scientist stands alone."},
        {"narration": "He hung two spheres from a wire.",
         "prompt": "The same scientist beside a tall box."},
        {"narration": "Their pull revealed Earth's mass.",
         "prompt": "The same scientist leaning in with a notebook."},
    ],
}


def test_parses_the_storyboard_shape():
    item = parse_any([STORYBOARD_ITEM])[0]
    assert item.style == "A scientist with round glasses and a long coat."
    assert len(item.beats) == 3
    assert item.beats[0] == Beat(
        "A scientist set out to weigh the world.", "The scientist stands alone."
    )


def test_description_is_derived_from_the_beat_narrations():
    item = parse_any([STORYBOARD_ITEM])[0]
    assert item.description == (
        "A scientist set out to weigh the world. He hung two spheres from a "
        "wire. Their pull revealed Earth's mass."
    )


def test_derived_description_overrides_a_stale_stored_one():
    stale = dict(STORYBOARD_ITEM, description="something else entirely")
    assert parse_any([stale])[0].description.startswith("A scientist set out")


def test_image_prompts_are_derived_from_the_beats():
    item = parse_any([STORYBOARD_ITEM])[0]
    assert item.image_prompts == (
        "The scientist stands alone.",
        "The same scientist beside a tall box.",
        "The same scientist leaning in with a notebook.",
    )


def test_legacy_items_become_beats_with_empty_narration():
    item = parse_any([VALID_ITEM])[0]
    assert item.style == ""
    assert item.image_prompts == (
        "a dodo",
        "a dodo on a skateboard",
        "a dodo, watercolour",
    )
    assert all(beat.narration == "" for beat in item.beats)
    assert item.description == "A flightless bird. It lived on Mauritius."


def test_an_empty_beats_list_falls_back_to_image_prompts():
    # The review editor posts `beats: []` alongside legacy `image_prompts`.
    payload = dict(VALID_ITEM, beats=[])
    assert len(parse_any([payload])[0].beats) == 3


def test_rejects_a_beat_missing_its_prompt():
    broken = dict(STORYBOARD_ITEM, beats=[{"narration": "x"}])
    with pytest.raises(InvalidItemsError, match="item 1.*prompt"):
        parse_items([broken], expected_prompts=None)


def test_rejects_a_beat_missing_its_narration():
    broken = dict(STORYBOARD_ITEM, beats=[{"prompt": "x"}])
    with pytest.raises(InvalidItemsError, match="item 1 beat 1.*narration"):
        parse_items([broken], expected_prompts=None)


def test_storyboard_round_trips_through_disk(tmp_path):
    items = parse_any([STORYBOARD_ITEM])
    target = tmp_path / "list.json"
    save_items(items, target)
    assert load_items(target) == items


def test_saved_json_carries_style_and_beats(tmp_path):
    target = tmp_path / "list.json"
    save_items(parse_any([STORYBOARD_ITEM]), target)
    saved = json.loads(target.read_text())["items"][0]
    assert saved["style"] == "A scientist with round glasses and a long coat."
    assert saved["beats"][0]["narration"] == "A scientist set out to weigh the world."


def test_from_prompts_builds_narrationless_beats():
    item = Item.from_prompts("Dodo", "A bird.", ("a", "b"))
    assert item.image_prompts == ("a", "b")
    assert item.description == "A bird."


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
