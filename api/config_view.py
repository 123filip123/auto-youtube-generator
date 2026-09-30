"""Expose pipeline configuration to the UI, and override it for one run.

`config.py` reads its values at import time, so a per-run override cannot be
done through the environment. Instead the run worker swaps the module
attributes for the duration of the run and puts them back afterwards. That is
only safe because exactly one run executes at a time.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import config


@dataclass(frozen=True)
class OverridableField:
    """One config constant the UI is allowed to change for a single run."""

    name: str
    type: str  # "int" or "str"
    choices: tuple[str, ...] | None = None
    description: str = ""


OVERRIDABLE: tuple[OverridableField, ...] = (
    OverridableField(
        "MODEL_TIER",
        "str",
        config.tier_names(),
        "Cheap models to iterate with, or expensive ones to publish with. "
        "Sets the text and image models; anything set below wins over it.",
    ),
    OverridableField(
        "TEXT_MODEL", "str", None, "Writes the script and the drawing prompts."
    ),
    OverridableField("TTS_MODEL", "str", None, "Generates the narration."),
    OverridableField("TTS_VOICE", "str", None, "Narration voice."),
    OverridableField("IMAGE_MODEL", "str", None, "Generates the images."),
    OverridableField("IMAGE_SIZE", "str", None, "Generated image dimensions."),
    OverridableField(
        "IMAGE_QUALITY",
        "str",
        ("low", "medium", "high"),
        "Higher costs more and takes longer.",
    ),
    OverridableField(
        "STORYBOARD_STYLE", "str", None, "The drawing style every frame shares."
    ),
    OverridableField(
        "TARGET_VIDEO_SECONDS",
        "int",
        None,
        "Target spoken length. Section and image counts follow from it.",
    ),
    OverridableField("MAX_CONCURRENT_REQUESTS", "int", None, "Parallel OpenAI calls."),
    OverridableField("MAX_RETRIES", "int", None, "Attempts per call."),
    OverridableField("VIDEO_FPS", "int", None, "Frames per second."),
    OverridableField(
        "VIDEO_PRESET",
        "str",
        ("ultrafast", "veryfast", "fast", "medium", "slow"),
        "x264 preset. Faster presets render quicker at a larger file size.",
    ),
)

_BY_NAME = {field.name: field for field in OVERRIDABLE}


class ConfigOverrideError(ValueError):
    """A requested override names an unknown constant or an invalid value."""


def effective_config() -> dict[str, Any]:
    """Every config constant currently in force, newest overrides included."""
    return {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper() and not name.startswith("_")
    }


def _clean_int(field: OverridableField, value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigOverrideError(
            f"{field.name} must be a whole number, got {value!r}"
        ) from exc
    if number <= 0:
        raise ConfigOverrideError(
            f"{field.name} must be greater than zero, got {number}"
        )
    return number


def _clean_str(field: OverridableField, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigOverrideError(f"{field.name} must be a non-empty string")
    text = value.strip()
    if field.choices and text not in field.choices:
        raise ConfigOverrideError(
            f"{field.name} must be one of {', '.join(field.choices)}, got {text!r}"
        )
    return text


def validate_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce and check a raw override map, or raise `ConfigOverrideError`."""
    cleaned: dict[str, Any] = {}
    for name, value in raw.items():
        field = _BY_NAME.get(name)
        if field is None:
            raise ConfigOverrideError(f"{name} is not overridable")
        cleaned[name] = (
            _clean_int(field, value) if field.type == "int" else _clean_str(field, value)
        )
    return cleaned


def _expand_tier(overrides: dict[str, Any]) -> dict[str, Any]:
    """Turn a `MODEL_TIER` override into the constants that tier stands for.

    A tier is shorthand, not a setting the pipeline reads, so it has to be
    unpacked before the constants are swapped. Anything named explicitly
    alongside it wins, which is what lets you run the quality tier with one
    knob dialled back.
    """
    if "MODEL_TIER" not in overrides:
        return dict(overrides)
    expanded = config.tier_values(overrides["MODEL_TIER"])
    expanded.update(overrides)
    return expanded


@contextmanager
def apply_overrides(overrides: dict[str, Any]) -> Iterator[None]:
    """Swap config constants for the duration of the block, then restore them."""
    overrides = _expand_tier(overrides)
    previous = {name: getattr(config, name) for name in overrides}
    for name, value in overrides.items():
        setattr(config, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(config, name, value)
