import json

import pytest

from models import (
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
    with pytest.raises(InvalidItemsError, match="item 1.*3 image prompts.*got 1"):
        parse_items([broken], expected_prompts=3)


def test_allows_any_prompt_count_when_expected_is_none():
    loose = dict(VALID_ITEM, image_prompts=["a", "b"])
    assert len(parse_items([loose], expected_prompts=None)[0].image_prompts) == 2


def test_reports_the_offending_index():
    with pytest.raises(InvalidItemsError, match="item 2"):
        parse_items([VALID_ITEM, {"title": "x"}])


def test_round_trips_through_disk(tmp_path):
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    target = tmp_path / "list.json"
    save_items(items, target)
    assert load_items(target) == items


def test_saved_json_uses_the_envelope_shape(tmp_path):
    target = tmp_path / "list.json"
    save_items([Item("Dodo", "A bird.", ("a", "b", "c"))], target)
    assert "items" in json.loads(target.read_text())


def test_save_creates_parent_directories(tmp_path):
    target = tmp_path / "deep" / "nested" / "list.json"
    save_items([Item("Dodo", "A bird.", ("a", "b", "c"))], target)
    assert target.exists()


def test_items_to_json_is_readable():
    text = items_to_json([Item("Dodo", "A bird.", ("a", "b", "c"))])
    assert "\n" in text  # indented, not one long line


def test_parse_items_rejects_an_empty_image_prompt_list():
    # all([]) is True, so an empty list used to slip through and then break
    # the renderer, which needs at least one image per item.
    payload = {
        "items": [{"title": "Dodo", "description": "A bird.", "image_prompts": []}]
    }
    with pytest.raises(InvalidItemsError, match="image_prompts"):
        parse_items(payload, expected_prompts=None)
