"""The typed representation of a generated list item.

Stages pass `list[Item]` to each other rather than raw JSON strings, so parsing
and validation happen exactly once, right after the model responds.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import config


class InvalidItemsError(ValueError):
    """The generated item list is missing fields or structurally wrong."""


@dataclass(frozen=True)
class Item:
    title: str
    description: str
    image_prompts: tuple[str, ...]

    @property
    def narration(self) -> str:
        """The text handed to the text-to-speech model."""
        return f"{self.title}. {self.description}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "image_prompts": list(self.image_prompts),
        }


def _strip_markdown_fences(text: str) -> str:
    """Older saved files were written by a model that wrapped JSON in fences."""
    return text.replace("```json", "").replace("```", "").strip()


def _decode(raw: str | bytes | list | dict) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    text = raw.decode() if isinstance(raw, bytes) else raw
    try:
        return json.loads(_strip_markdown_fences(text))
    except json.JSONDecodeError as exc:
        raise InvalidItemsError(f"Model output was not valid JSON: {exc}") from exc


def _required_text(payload: dict, key: str, position: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidItemsError(
            f"item {position} is missing a usable '{key}' (got {value!r})"
        )
    return value.strip()


def parse_items(
    raw: str | bytes | list | dict,
    *,
    expected_prompts: int | None = config.IMAGE_PROMPTS_PER_ITEM,
) -> list[Item]:
    """Validate and convert model output into a list of `Item`.

    Accepts the `{"items": [...]}` envelope returned by structured outputs, a
    bare `[...]` list (the shape of older saved files), or already-decoded
    Python objects. Pass `expected_prompts=None` to skip the prompt-count check.
    """
    decoded = _decode(raw)

    if isinstance(decoded, dict):
        decoded = decoded.get("items")

    if not isinstance(decoded, list):
        raise InvalidItemsError(
            f"Expected a list of items, got {type(decoded).__name__}"
        )
    if not decoded:
        raise InvalidItemsError("Model returned no items")

    items: list[Item] = []
    for position, payload in enumerate(decoded, start=1):
        if not isinstance(payload, dict):
            raise InvalidItemsError(
                f"item {position} is not an object (got {type(payload).__name__})"
            )

        title = _required_text(payload, "title", position)
        description = _required_text(payload, "description", position)

        prompts = payload.get("image_prompts")
        if (
            not isinstance(prompts, list)
            or not prompts
            or not all(isinstance(p, str) and p.strip() for p in prompts)
        ):
            raise InvalidItemsError(
                f"item {position} is missing a usable 'image_prompts' list"
            )
        if expected_prompts is not None and len(prompts) != expected_prompts:
            raise InvalidItemsError(
                f"item {position} needs exactly {expected_prompts} image prompts, "
                f"got {len(prompts)}"
            )

        items.append(
            Item(
                title=title,
                description=description,
                image_prompts=tuple(p.strip() for p in prompts),
            )
        )

    return items


def items_to_json(items: Sequence[Item]) -> str:
    return json.dumps({"items": [item.to_dict() for item in items]}, indent=2)


def save_items(items: Sequence[Item], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(items_to_json(items), encoding="utf-8")


def load_items(path: Path) -> list[Item]:
    return parse_items(path.read_text(encoding="utf-8"), expected_prompts=None)
