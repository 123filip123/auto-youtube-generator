"""The typed representation of a generated sectioned script.

Stages pass a `Script` to each other rather than raw JSON strings, so parsing
and validation happen exactly once, right after the model responds.
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from utils.timing import speaking_seconds


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
        raise InvalidScriptError(f"Script was not valid JSON: {exc}") from exc


class InvalidScriptError(ValueError):
    """The generated script is missing fields or structurally wrong."""


@dataclass(frozen=True)
class Section:
    """One labelled passage of narration and the shots laid over it.

    `start` and `end` are outputs, never inputs: estimated when the script is
    written, overwritten with measured values once the audio exists.
    """

    label: str
    narration: str
    prompts: tuple[str, ...] = ()
    start: float = 0.0
    end: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "narration": self.narration,
            "start": self.start,
            "end": self.end,
            "prompts": list(self.prompts),
        }


@dataclass(frozen=True)
class Script:
    topic: str
    title: str
    style: str = ""
    sections: tuple[Section, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "title": self.title,
            "style": self.style,
            "sections": [section.to_dict() for section in self.sections],
        }


def _required_script_text(payload: dict, key: str, position: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidScriptError(
            f"section {position} is missing a usable '{key}' (got {value!r})"
        )
    return value.strip()


def _parse_prompts(payload: dict, position: int) -> tuple[str, ...]:
    """Prompts are optional: call 1 writes sections before call 2 fills them."""
    raw = payload.get("prompts")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise InvalidScriptError(
            f"section {position} has a malformed 'prompts' list "
            f"(got {type(raw).__name__})"
        )
    prompts: list[str] = []
    for prompt_position, entry in enumerate(raw, start=1):
        if not isinstance(entry, str) or not entry.strip():
            raise InvalidScriptError(
                f"section {position} prompt {prompt_position} is not a "
                f"non-empty string (got {entry!r})"
            )
        prompts.append(entry.strip())
    return tuple(prompts)


def parse_script(raw: str | bytes | dict, *, topic: str = "") -> Script:
    """Validate and convert model output into a `Script`.

    `topic` is supplied by the caller rather than the model on first parse;
    a payload that already carries one (a saved file) keeps its own.
    """
    decoded = _decode(raw)
    if not isinstance(decoded, dict):
        raise InvalidScriptError(
            f"Expected a script object, got {type(decoded).__name__}"
        )

    title = decoded.get("title")
    if not isinstance(title, str) or not title.strip():
        raise InvalidScriptError(f"script is missing a usable 'title' (got {title!r})")

    raw_sections = decoded.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise InvalidScriptError("script needs at least one section")

    sections: list[Section] = []
    for position, payload in enumerate(raw_sections, start=1):
        if not isinstance(payload, dict):
            raise InvalidScriptError(
                f"section {position} is not an object "
                f"(got {type(payload).__name__})"
            )
        sections.append(
            Section(
                label=_required_script_text(payload, "label", position),
                narration=_required_script_text(payload, "narration", position),
                prompts=_parse_prompts(payload, position),
                start=float(payload.get("start") or 0.0),
                end=float(payload.get("end") or 0.0),
            )
        )

    return Script(
        topic=str(decoded.get("topic") or topic).strip(),
        title=title.strip(),
        style=str(decoded.get("style") or "").strip(),
        sections=tuple(sections),
    )


def with_durations(script: Script, durations: Sequence[float]) -> Script:
    """Lay the sections end to end using `durations`, one per section."""
    if len(durations) != len(script.sections):
        raise ValueError(
            f"script has {len(script.sections)} sections but "
            f"{len(durations)} duration(s) were supplied"
        )

    timed: list[Section] = []
    start = 0.0
    for section, duration in zip(script.sections, durations):
        end = start + duration
        timed.append(replace(section, start=start, end=end))
        start = end
    return replace(script, sections=tuple(timed))


def with_estimated_timings(script: Script) -> Script:
    """Fill start/end from each narration's estimated speaking time."""
    return with_durations(
        script, [speaking_seconds(section.narration) for section in script.sections]
    )


def script_to_json(script: Script) -> str:
    return json.dumps(script.to_dict(), indent=2)


def save_script(script: Script, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script_to_json(script), encoding="utf-8")


def load_script(path: Path) -> Script:
    return parse_script(path.read_text(encoding="utf-8"))
