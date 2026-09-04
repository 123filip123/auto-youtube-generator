import json

import pytest

from models import (
    Beat,
    InvalidItemsError,
    Item,
    items_to_json,
    load_items,
    parse_items,
    save_items,
)

VALID_ITEM = {
    "title": "Dodo",
    "description": "A flightless bird. It lived on Mauritius.",
    "image_prompts": ["a dodo", "a dodo on a skateboard", "a dodo, watercolour"],
}


def test_parses_envelope_shape():
    items = parse_items(json.dumps({"items": [VALID_ITEM]}))
    assert len(items) == 1
    assert items[0].title == "Dodo"
    assert items[0].image_prompts == (
        "a dodo",
        "a dodo on a skateboard",
        "a dodo, watercolour",
    )


def test_parses_bare_list_shape():
    items = parse_items(json.dumps([VALID_ITEM]))
    assert len(items) == 1


def test_parses_already_decoded_python_objects():
    items = parse_items([VALID_ITEM])
    assert items[0].title == "Dodo"


def test_strips_markdown_fences_for_legacy_files():
    fenced = "```json\n" + json.dumps([VALID_ITEM]) + "\n```"
    assert len(parse_items(fenced)) == 1


def test_narration_joins_title_and_description():
    item = parse_items([VALID_ITEM])[0]
    assert item.narration == "Dodo. A flightless bird. It lived on Mauritius."


def test_item_is_immutable():
    item = parse_items([VALID_ITEM])[0]
    with pytest.raises(Exception):
        item.title = "changed"


def test_rejects_malformed_json():
    with pytest.raises(InvalidItemsError, match="not valid JSON"):
        parse_items("{oh no")


def test_rejects_empty_list():
    with pytest.raises(InvalidItemsError, match="no items"):
        parse_items("[]")


def test_rejects_missing_field():
    broken = {"title": "Dodo", "image_prompts": ["a", "b", "c"]}
    with pytest.raises(InvalidItemsError, match="item 1.*description"):
        parse_items([broken])


def test_rejects_blank_title():
    broken = dict(VALID_ITEM, title="   ")
    with pytest.raises(InvalidItemsError, match="item 1.*title"):
        parse_items([broken])


def test_rejects_wrong_prompt_count():
    broken = dict(VALID_ITEM, image_prompts=["only one"])
    with pytest.raises(InvalidItemsError, match="item 1.*3 story beats.*got 1"):
        parse_items([broken], expected_prompts=3)


def test_allows_any_prompt_count_when_expected_is_none():
    loose = dict(VALID_ITEM, image_prompts=["a", "b"])
    assert len(parse_items([loose], expected_prompts=None)[0].image_prompts) == 2


def test_reports_the_offending_index():
    with pytest.raises(InvalidItemsError, match="item 2"):
        parse_items([VALID_ITEM, {"title": "x"}])


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
    item = parse_items([STORYBOARD_ITEM])[0]
    assert item.style == "A scientist with round glasses and a long coat."
    assert len(item.beats) == 3
    assert item.beats[0] == Beat(
        "A scientist set out to weigh the world.", "The scientist stands alone."
    )


def test_description_is_derived_from_the_beat_narrations():
    item = parse_items([STORYBOARD_ITEM])[0]
    assert item.description == (
        "A scientist set out to weigh the world. He hung two spheres from a "
        "wire. Their pull revealed Earth's mass."
    )


def test_derived_description_overrides_a_stale_stored_one():
    stale = dict(STORYBOARD_ITEM, description="something else entirely")
    assert parse_items([stale])[0].description.startswith("A scientist set out")


def test_image_prompts_are_derived_from_the_beats():
    item = parse_items([STORYBOARD_ITEM])[0]
    assert item.image_prompts == (
        "The scientist stands alone.",
        "The same scientist beside a tall box.",
        "The same scientist leaning in with a notebook.",
    )


def test_legacy_items_become_beats_with_empty_narration():
    item = parse_items([VALID_ITEM])[0]
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
    assert len(parse_items([payload])[0].beats) == 3


def test_rejects_a_beat_missing_its_prompt():
    broken = dict(STORYBOARD_ITEM, beats=[{"narration": "x"}])
    with pytest.raises(InvalidItemsError, match="item 1.*prompt"):
        parse_items([broken], expected_prompts=None)


def test_rejects_a_beat_missing_its_narration():
    broken = dict(STORYBOARD_ITEM, beats=[{"prompt": "x"}])
    with pytest.raises(InvalidItemsError, match="item 1 beat 1.*narration"):
        parse_items([broken], expected_prompts=None)


def test_storyboard_round_trips_through_disk(tmp_path):
    items = parse_items([STORYBOARD_ITEM])
    target = tmp_path / "list.json"
    save_items(items, target)
    assert load_items(target) == items


def test_saved_json_carries_style_and_beats(tmp_path):
    target = tmp_path / "list.json"
    save_items(parse_items([STORYBOARD_ITEM]), target)
    saved = json.loads(target.read_text())["items"][0]
    assert saved["style"] == "A scientist with round glasses and a long coat."
    assert saved["beats"][0]["narration"] == "A scientist set out to weigh the world."


def test_from_prompts_builds_narrationless_beats():
    item = Item.from_prompts("Dodo", "A bird.", ("a", "b"))
    assert item.image_prompts == ("a", "b")
    assert item.description == "A bird."
