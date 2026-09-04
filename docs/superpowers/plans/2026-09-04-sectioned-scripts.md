# Sectioned Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the list-of-items video format with one continuous narrated script divided into free-form sections, where images are derived from narration length and chained within each section.

**Architecture:** Two AI calls — one writes the script as prose sections, a second sees the whole script and returns a global style sheet plus every image prompt. Shot counts are computed from narration length, never authored. Images generate as a sequential chain inside each section, resetting at every section boundary, with sections running in parallel. Video assembly splits each section's *measured* audio duration evenly across its shots.

**Tech Stack:** Python 3.12, pytest, FastAPI, Pydantic, OpenAI SDK, tenacity, moviepy, Pillow; React 19 + TypeScript + vitest on the frontend.

**Spec:** `docs/superpowers/specs/2026-09-04-sectioned-script-design.md`

## Global Constraints

- `SECONDS_PER_IMAGE = 2.5` — new config constant, replaces `SECONDS_PER_FRAME = 4.0`.
- `TARGET_VIDEO_SECONDS = 85` — new config constant, replaces `IMAGE_PROMPTS_PER_ITEM`.
- `NARRATION_WORDS_PER_SECOND = 3.15` and `NARRATION_SENTENCE_PAUSE_SECONDS = 1.6` keep their existing values and become load-bearing in three places.
- `target_seconds` accepts 15–180 at the API boundary.
- `word_budget` uses `avg_words_per_sentence = 13` as its default.
- `count_sentences` counts runs of `.`, `!` or `?` (a consecutive run counts once) and returns at least 1 for any non-empty narration, 0 for empty.
- Shot-count mismatches from call 2 are tolerated and honoured, never corrected. Only a missing or empty section triggers a repair call — exactly one, then fail.
- `frontend/src/lib/types.ts` mirrors `api/schemas.py` field for field. Always change both in the same task.
- Every stage module keeps the existing `Job` / `TaskResult` / `run_all` contract from `utils/openai_support.py`. Do not modify that module.

## Sequencing Strategy

`Item` and `Beat` are load-bearing across 22 files. Deleting them up front would leave the suite red for a dozen tasks, so this plan **builds the new path alongside the old one** (Tasks 1–10), then **cuts over and deletes the old path in a single task** (Task 11). The suite stays green after every task. Tasks 1–10 add code that nothing calls yet; that is deliberate.

## File Structure

**New files:**

| File | Responsibility |
|---|---|
| `utils/timing.py` | Pure narration→duration arithmetic: sentence counting, speaking time, shot count, word budget. No I/O, no config mutation. |
| `scripts/ai/generate_script/generate_script.py` | AI call 1. Topic + target seconds → `Script` with sections and narration. |
| `scripts/ai/generate_prompts/generate_prompts.py` | AI call 2. `Script` → same `Script` with `style` and per-section `prompts` filled. |
| `scripts/non_ai/compose_frames/compose_frames.py` | Fan composition jobs out per shot. |
| `scripts/non_ai/compose_frames/utils.py` | Single-frame composition: blurred backdrop, centred image, no text. |
| `tests/test_timing.py`, `tests/test_generate_script.py`, `tests/test_generate_prompts.py`, `tests/test_compose.py` | Mirror their modules 1:1, as the suite already does. |

**Modified:** `config.py`, `models.py`, `utils/paths.py`, `scripts/ai/generate_images/generate_images.py`, `scripts/ai/generate_audios/*`, `scripts/non_ai/generate_video_short/*`, `scripts/non_ai/save_to_generated_data/*`, `pipeline.py`, `main.py`, `api/{schemas,routes,runs,archives,config_view}.py`, `frontend/src/lib/{types,api}.ts`, `frontend/src/components/ItemEditor.tsx`, `frontend/src/pages/{NewRunPage,RunPage,ArchiveDetailPage,ArchivesPage}.tsx`, `README.md`, `.env.example`.

**Deleted at Task 11:** `scripts/ai/generate_list/`, `scripts/non_ai/create_titled_images_short/`, `tests/test_generate_list.py`, `tests/test_titled_images.py`, and `Item`/`Beat`/`parse_items`/`save_items`/`load_items` from `models.py`.

---

### Task 1: Timing arithmetic

The pure functions every later task depends on. No I/O — this is the one place the pause correction lives, and getting it wrong produces videos 40% over target.

**Files:**
- Create: `utils/timing.py`
- Modify: `config.py`
- Test: `tests/test_timing.py`

**Interfaces:**
- Consumes: `config.NARRATION_WORDS_PER_SECOND`, `config.NARRATION_SENTENCE_PAUSE_SECONDS`.
- Produces: `count_sentences(narration: str) -> int`, `speaking_seconds(narration: str) -> float`, `shot_count(narration: str) -> int`, `word_budget(target_seconds: float, avg_words_per_sentence: int = 13) -> int`, and config constants `SECONDS_PER_IMAGE: float`, `TARGET_VIDEO_SECONDS: int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_timing.py`:

```python
import pytest

import config
from utils.timing import count_sentences, shot_count, speaking_seconds, word_budget


@pytest.mark.parametrize(
    "narration, expected",
    [
        ("", 0),
        ("   ", 0),
        ("No terminal punctuation", 1),
        ("One sentence.", 1),
        ("Hello. World!", 2),
        ("Wait... what?", 2),
        ("Really?! Yes.", 2),
    ],
)
def test_count_sentences(narration, expected):
    assert count_sentences(narration) == expected


def test_speaking_seconds_includes_a_pause_per_sentence():
    # 30 words over two sentences: 30/3.15 speaking + 2*1.6 pause.
    narration = " ".join(["word"] * 29) + ". Done."
    expected = 30 / config.NARRATION_WORDS_PER_SECOND + 2 * config.NARRATION_SENTENCE_PAUSE_SECONDS
    assert speaking_seconds(narration) == pytest.approx(expected)


def test_shot_count_divides_speaking_time_by_seconds_per_image():
    # 30 words, 2 sentences -> 12.72s -> 12.72/2.5 = 5.09 -> 5 shots.
    narration = " ".join(["word"] * 29) + ". Done."
    assert shot_count(narration) == 5


def test_shot_count_is_at_least_one():
    assert shot_count("Hi.") == 1
    assert shot_count("") == 1


def test_word_budget_accounts_for_the_inter_sentence_pause():
    # The naive figure is 85 * 3.15 = 268, which renders as ~118 seconds.
    assert word_budget(85) == 193
    assert word_budget(85) < 85 * config.NARRATION_WORDS_PER_SECOND


def test_word_budget_scales_with_target():
    assert word_budget(170) == 2 * word_budget(85) or word_budget(170) > word_budget(85)


def test_shot_count_reads_config_at_call_time(monkeypatch):
    narration = " ".join(["word"] * 29) + ". Done."
    monkeypatch.setattr(config, "SECONDS_PER_IMAGE", 5.0)
    assert shot_count(narration) == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_timing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.timing'`

- [ ] **Step 3: Add the two config constants**

In `config.py`, replace the `IMAGE_PROMPTS_PER_ITEM` and `SECONDS_PER_FRAME` block under `# --- Pipeline shape ---` with the following. Leave `IMAGE_PROMPTS_PER_ITEM` and `SECONDS_PER_FRAME` in place for now — Task 11 removes them, and the old pipeline still reads them until then.

```python
# How long a script should run, and how long one image holds. Image count is
# a consequence of narration length, not a knob: see utils/timing.py.
TARGET_VIDEO_SECONDS = _env_int("TARGET_VIDEO_SECONDS", 85)
SECONDS_PER_IMAGE = 2.5
```

- [ ] **Step 4: Write the implementation**

Create `utils/timing.py`:

```python
"""Turn narration text into the timings the pipeline plans against.

Every duration here is derived, never authored: the model writes prose to a
word budget and these functions decide how long it takes to speak and
therefore how many images ride over it.

The inter-sentence pause is what makes this non-obvious. The voice leaves
~1.6s of silence after every sentence whatever the sentence says, so two
paragraphs of equal word count but different sentence counts have materially
different runtimes. Ignoring that term under-counts shots and overshoots the
target length.
"""

import re

import config

# A run of consecutive terminators is one sentence end, so "Wait..." costs
# one pause rather than three.
_SENTENCE_END = re.compile(r"[.!?]+")


def count_sentences(narration: str) -> int:
    """How many sentence-ending pauses the voice will take.

    Non-empty narration written without terminal punctuation is still one
    spoken sentence, so the floor is 1.
    """
    text = narration.strip()
    if not text:
        return 0
    return max(1, len(_SENTENCE_END.findall(text)))


def speaking_seconds(narration: str) -> float:
    """How long `narration` takes to speak aloud, pauses included."""
    words = len(narration.split())
    return (
        words / config.NARRATION_WORDS_PER_SECOND
        + count_sentences(narration) * config.NARRATION_SENTENCE_PAUSE_SECONDS
    )


def shot_count(narration: str) -> int:
    """How many images ride over `narration`. Always at least one."""
    return max(1, round(speaking_seconds(narration) / config.SECONDS_PER_IMAGE))


def word_budget(target_seconds: float, avg_words_per_sentence: int = 13) -> int:
    """The total spoken-word budget for a script of `target_seconds`.

    The naive figure — target times words-per-second — ignores the pause and
    overshoots badly: 85 seconds budgets 268 words that way, which renders as
    roughly 118 seconds. Costing a whole sentence, speech plus pause, and
    dividing gives ~193 instead.
    """
    seconds_per_sentence = (
        avg_words_per_sentence / config.NARRATION_WORDS_PER_SECOND
        + config.NARRATION_SENTENCE_PAUSE_SECONDS
    )
    return round(target_seconds / seconds_per_sentence * avg_words_per_sentence)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_timing.py -v`
Expected: PASS, 13 tests.

- [ ] **Step 6: Run the whole suite to confirm nothing regressed**

Run: `venv/bin/pytest`
Expected: PASS — the new config constants are additive.

- [ ] **Step 7: Commit**

```bash
git add utils/timing.py tests/test_timing.py config.py
git commit -m "feat: derive shot counts and word budgets from narration timing"
```

---

### Task 2: The Script and Section model

`Script`/`Section` land beside `Item`/`Beat`. Nothing calls them yet.

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `utils.timing.speaking_seconds`.
- Produces: `Section(label, narration, prompts=(), start=0.0, end=0.0)`, `Script(topic, title, style="", sections=())`, `InvalidScriptError`, `parse_script(raw, *, topic="") -> Script`, `script_to_json(script) -> str`, `save_script(script, path)`, `load_script(path) -> Script`, `with_durations(script, durations) -> Script`, `with_estimated_timings(script) -> Script`. `Section.to_dict()` and `Script.to_dict()` return the JSON shapes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'InvalidScriptError' from 'models'`

- [ ] **Step 3: Write the implementation**

Append to `models.py` (keep everything already there):

```python
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
```

Add these to the imports at the top of `models.py`:

```python
from dataclasses import dataclass, replace
from utils.timing import speaking_seconds
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_models.py -v`
Expected: PASS, including the pre-existing `Item` tests.

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add the Script and Section model beside Item"
```

---

### Task 3: Section-shaped output paths

**Files:**
- Modify: `utils/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `COMPOSED_IMAGE_OUTPUT_DIR`, `SCRIPT_FILENAME = "script.json"`, `section_image_path(section_number, shot_number) -> Path`, `section_audio_path(section_number) -> Path`, `composed_image_path(section_number, shot_number) -> Path`, `script_path() -> Path`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_paths.py`:

```python
from utils.paths import (
    COMPOSED_IMAGE_OUTPUT_DIR,
    composed_image_path,
    ensure_output_dirs,
    script_path,
    section_audio_path,
    section_image_path,
)


def test_section_image_path_zero_pads_both_numbers():
    assert section_image_path(1, 3).name == "section_01_shot_03.png"
    assert section_image_path(12, 10).name == "section_12_shot_10.png"


def test_section_audio_path_is_one_file_per_section():
    assert section_audio_path(2).name == "section_02.mp3"


def test_composed_image_path_is_prefixed_and_separate():
    path = composed_image_path(1, 2)
    assert path.name == "composed_section_01_shot_02.png"
    assert path.parent == COMPOSED_IMAGE_OUTPUT_DIR


def test_script_path_is_named_script_json():
    assert script_path().name == "script.json"


def test_ensure_output_dirs_creates_the_composed_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    assert (tmp_path / COMPOSED_IMAGE_OUTPUT_DIR).is_dir()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_paths.py -v`
Expected: FAIL — `ImportError: cannot import name 'COMPOSED_IMAGE_OUTPUT_DIR'`

- [ ] **Step 3: Write the implementation**

In `utils/paths.py`, add the directory constant next to the existing ones and include it in `ALL_OUTPUT_DIRS`:

```python
COMPOSED_IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "composed_image_output"

ALL_OUTPUT_DIRS = (
    AUDIO_OUTPUT_DIR,
    IMAGE_OUTPUT_DIR,
    JSON_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    COMPOSED_IMAGE_OUTPUT_DIR,
    VIDEO_OUTPUT_DIR,
)

SCRIPT_FILENAME = "script.json"
```

Then add the path helpers beside the existing ones:

```python
def section_image_path(section_number: int, shot_number: int) -> Path:
    return (
        IMAGE_OUTPUT_DIR
        / f"section_{section_number:02d}_shot_{shot_number:02d}.png"
    )


def section_audio_path(section_number: int) -> Path:
    return AUDIO_OUTPUT_DIR / f"section_{section_number:02d}.mp3"


def composed_image_path(section_number: int, shot_number: int) -> Path:
    return (
        COMPOSED_IMAGE_OUTPUT_DIR
        / f"composed_section_{section_number:02d}_shot_{shot_number:02d}.png"
    )


def script_path() -> Path:
    return JSON_OUTPUT_DIR / SCRIPT_FILENAME
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add utils/paths.py tests/test_paths.py
git commit -m "feat: add section-shaped output paths"
```

---

### Task 4: AI call 1 — the script writer

**Files:**
- Create: `scripts/ai/generate_script/__init__.py`, `scripts/ai/generate_script/generate_script.py`
- Test: `tests/test_generate_script.py`

**Interfaces:**
- Consumes: `utils.timing.word_budget`, `models.parse_script`, `models.with_estimated_timings`, `utils.openai_support.with_retry`, `utils.open_ai_client.get_open_ai_client`.
- Produces: `SCRIPT_SYSTEM_MESSAGE`, `SCRIPT_JSON_SCHEMA`, `build_script_message(topic, target_seconds) -> str`, `generate_script(topic, target_seconds=None, *, client=None) -> Script`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_script.py`:

```python
import json
from types import SimpleNamespace

import pytest

import config
from models import InvalidScriptError
from scripts.ai.generate_script.generate_script import (
    SCRIPT_JSON_SCHEMA,
    build_script_message,
    generate_script,
)
from utils.timing import word_budget


def build_payload(sections=4):
    return {
        "title": "Wolves Domesticated Themselves",
        "sections": [
            {"label": f"SECTION {i}", "narration": f"Narration number {i}."}
            for i in range(1, sections + 1)
        ],
    }


class FakeClient:
    """Records the request and replays a canned response."""

    def __init__(self, content):
        self.content = content
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_returns_a_typed_script_carrying_the_topic():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("how dogs evolved from wolves", 85, client=client)
    assert script.topic == "how dogs evolved from wolves"
    assert script.title == "Wolves Domesticated Themselves"
    assert len(script.sections) == 4
    assert script.sections[0].label == "SECTION 1"


def test_sections_have_no_prompts_yet():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("wolves", 85, client=client)
    assert all(section.prompts == () for section in script.sections)


def test_estimated_timings_are_filled_in():
    client = FakeClient(json.dumps(build_payload()))
    script = generate_script("wolves", 85, client=client)
    assert script.sections[0].start == 0.0
    assert script.sections[-1].end > 0
    assert script.sections[1].start == pytest.approx(script.sections[0].end)


def test_requests_a_strict_json_schema():
    client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", 85, client=client)
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == SCRIPT_JSON_SCHEMA


def test_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr(config, "TEXT_MODEL", "test-model")
    client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", 85, client=client)
    assert client.calls[0]["model"] == "test-model"


def test_defaults_the_target_to_config():
    monkeypatchless_client = FakeClient(json.dumps(build_payload()))
    generate_script("wolves", client=monkeypatchless_client)
    sent = monkeypatchless_client.calls[0]["messages"][1]["content"]
    assert str(config.TARGET_VIDEO_SECONDS) in sent


def test_message_states_the_pause_corrected_word_budget():
    message = build_script_message("wolves", 85)
    assert str(word_budget(85)) in message
    # The naive figure would be 267; it must not appear.
    assert str(round(85 * config.NARRATION_WORDS_PER_SECOND)) not in message


def test_message_keeps_the_safety_and_copyright_guidance():
    message = build_script_message("wolves", 85)
    assert "family-friendly" in message
    assert "copyrighted" in message.lower()


def test_rejects_a_target_below_the_floor():
    with pytest.raises(ValueError, match="at least"):
        generate_script("wolves", 0, client=FakeClient("{}"))


def test_surfaces_a_malformed_response():
    client = FakeClient(json.dumps({"title": "T", "sections": []}))
    with pytest.raises(InvalidScriptError):
        generate_script("wolves", 85, client=client)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_generate_script.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ai.generate_script'`

- [ ] **Step 3: Create the package**

```bash
mkdir -p scripts/ai/generate_script
touch scripts/ai/generate_script/__init__.py
```

- [ ] **Step 4: Write the implementation**

Create `scripts/ai/generate_script/generate_script.py`:

```python
"""Ask the model for one narrated script, divided into free-form sections."""

import config
from models import Script, parse_script, with_estimated_timings
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry
from utils.timing import word_budget

# Anything shorter than this cannot carry a hook and a payoff.
MIN_TARGET_SECONDS = 15

SCRIPT_SYSTEM_MESSAGE = (
    "You are a short-form video writer. You write one continuous spoken "
    "script for a vertical video, divided into labelled sections that build "
    "on each other. Always ensure all content is family-friendly and "
    "appropriate for all audiences."
)

SCRIPT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": (
                "The video title: short, concrete, and stating the surprise "
                "rather than teasing it."
            ),
        },
        "sections": {
            "type": "array",
            "description": "The sections of the script, in spoken order.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": (
                            "A short upper-case name for this section's job, "
                            "chosen by you, e.g. HOOK or WAIT, WHAT?"
                        ),
                    },
                    "narration": {
                        "type": "string",
                        "description": (
                            "The spoken prose for this section: one to four "
                            "sentences, read aloud continuously."
                        ),
                    },
                },
                "required": ["label", "narration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "sections"],
    "additionalProperties": False,
}


def build_script_message(topic: str, target_seconds: int) -> str:
    """The user message for call 1.

    The word budget is pause-corrected — see `utils.timing.word_budget`. Handing
    the model the naive words-per-second figure produces scripts ~40% long.
    """
    budget = word_budget(target_seconds)
    return (
        f"Write the script for a {target_seconds}-second vertical video on: "
        f"'{topic}'.\n"
        f"\n"
        f"Total spoken length must be about {budget} words across all "
        f"sections. This is a spoken-word budget that already accounts for "
        f"the pauses between sentences, so treat it as a hard ceiling.\n"
        f"\n"
        f"STRUCTURE:\n"
        f"- Divide the script into sections. You choose how many and what to "
        f"call them; four to seven works well at this length.\n"
        f"- Give each section a short upper-case label naming its job in the "
        f"video, for example HOOK, SETUP, THE TWIST, or WAIT, WHAT?\n"
        f"- The first section must hook the viewer in one or two sentences. "
        f"The last section must end on a call to action.\n"
        f"- Sections in between carry the argument: set up the situation, "
        f"turn it, give the evidence, land the payoff.\n"
        f"\n"
        f"VOICE:\n"
        f"- Address the viewer directly as 'you'. Write the way a person "
        f"talks, contractions included.\n"
        f"- Open on a concrete, surprising, specific fact. Never open by "
        f"summarising what the video will cover.\n"
        f"- Never write meta narration such as 'in this video we'll explore' "
        f"or 'let's dive in'.\n"
        f"- Prefer specific numbers, names and dates over vague claims.\n"
        f"- Vary sentence length. Short sentences land the turns.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES:\n"
        f"- All content must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Avoid any content that could be considered violent, graphic, or "
        f"inappropriate\n"
        f"- Ensure the script is educational, informative, or entertaining in "
        f"a wholesome way\n"
        f"- If the topic involves potentially sensitive subjects, focus on "
        f"positive, educational, or neutral representations\n"
        f"\n"
        f"COPYRIGHT AND INTELLECTUAL PROPERTY GUIDELINES:\n"
        f"- NEVER reference copyrighted characters, brands, or intellectual "
        f"property\n"
        f"- Avoid specific character names like 'Yoda', 'Mickey Mouse', "
        f"'Superman', 'Mario', etc.\n"
        f"- Avoid famous logos, brand names, or trademarked symbols\n"
        f"- Focus on visual concepts, emotions, and themes rather than "
        f"specific copyrighted entities"
    )


@with_retry
def _request_script(client, topic: str, target_seconds: int) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": SCRIPT_SYSTEM_MESSAGE},
            {"role": "user", "content": build_script_message(topic, target_seconds)},
        ],
        temperature=config.TEXT_TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "video_script",
                "strict": True,
                "schema": SCRIPT_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def generate_script(
    topic: str, target_seconds: int | None = None, *, client=None
) -> Script:
    """Write one script for `topic`, roughly `target_seconds` long.

    Raises `InvalidScriptError` if the model's output does not match the
    expected shape. The returned script carries estimated timings; nothing
    consumes them until the archive rewrites them from measured audio.
    """
    target = (
        config.TARGET_VIDEO_SECONDS if target_seconds is None else int(target_seconds)
    )
    if target < MIN_TARGET_SECONDS:
        raise ValueError(
            f"target_seconds must be at least {MIN_TARGET_SECONDS}, got {target}"
        )

    client = client or get_open_ai_client()
    content = _request_script(client, topic, target)
    return with_estimated_timings(parse_script(content or "", topic=topic))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_generate_script.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/generate_script tests/test_generate_script.py
git commit -m "feat: generate a sectioned script from a topic and target length"
```

---

### Task 5: AI call 2 — the image-prompt writer

Sees the whole script at once and returns the global style sheet plus every prompt. Merges results **by index, not by label** — labels are free-form and may repeat.

**Files:**
- Create: `scripts/ai/generate_prompts/__init__.py`, `scripts/ai/generate_prompts/generate_prompts.py`
- Test: `tests/test_generate_prompts.py`

**Interfaces:**
- Consumes: `models.Script`, `models.Section`, `utils.timing.shot_count`.
- Produces: `PROMPTS_SYSTEM_MESSAGE`, `PROMPTS_JSON_SCHEMA`, `build_prompts_message(script, budgets) -> str`, `shot_budgets(script) -> list[int]`, `PromptGenerationError`, `generate_prompts(script, *, client=None) -> Script`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_prompts.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_generate_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ai.generate_prompts'`

- [ ] **Step 3: Create the package**

```bash
mkdir -p scripts/ai/generate_prompts
touch scripts/ai/generate_prompts/__init__.py
```

- [ ] **Step 4: Write the implementation**

Create `scripts/ai/generate_prompts/generate_prompts.py`:

```python
"""Turn a finished script into a style sheet and one image prompt per shot.

This call sees the whole script at once, which is the point: it lets the model
plan a visual arc across the video and author a style sheet that serves every
section rather than only the first.
"""

import json
from dataclasses import replace
from typing import Sequence

import config
from models import Script
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry
from utils.timing import shot_count


class PromptGenerationError(RuntimeError):
    """The model failed to return usable prompts for every section."""


PROMPTS_SYSTEM_MESSAGE = (
    "You are a storyboard artist. Given a narrated script, you design the "
    "sequence of simple line drawings that illustrates it. Always ensure all "
    "content is family-friendly and appropriate for all audiences."
)

PROMPTS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "style": {
            "type": "string",
            "description": (
                "The recurring figure(s) and setting for the whole video, "
                "described concretely enough to be redrawn identically in "
                "every frame, naming a distinct vivid colour for each element."
            ),
        },
        "sections": {
            "type": "array",
            "description": (
                "One entry per script section, in the same order as given."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "The section's label, echoed back.",
                    },
                    "prompts": {
                        "type": "array",
                        "description": "The drawings for this section, in order.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["label", "prompts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["style", "sections"],
    "additionalProperties": False,
}


def shot_budgets(script: Script) -> list[int]:
    """How many shots each section's narration earns."""
    return [shot_count(section.narration) for section in script.sections]


def build_prompts_message(script: Script, budgets: Sequence[int]) -> str:
    """The user message for call 2: the whole script plus each shot budget."""
    listing = "\n\n".join(
        f"SECTION {position} — {section.label} — {budget} drawing(s)\n"
        f"{section.narration}"
        for position, (section, budget) in enumerate(
            zip(script.sections, budgets), start=1
        )
    )
    return (
        f"Here is the full script for a vertical video titled "
        f"'{script.title}'. Design the drawings for it.\n"
        f"\n"
        f"{listing}\n"
        f"\n"
        f"Return one entry per section, in this exact order, with the number "
        f"of drawings shown above for each.\n"
        f"\n"
        f"FIRST, write the 'style' sheet: the recurring figure(s) and setting "
        f"for the whole video — their build, hair, clothing, props and "
        f"surroundings, and the colour of each — described concretely enough "
        f"that an illustrator could redraw them identically in every frame. "
        f"Name a distinct, vivid colour for each element and avoid white, "
        f"grey and black. Describe only what is drawn; do not name a medium "
        f"or an art style. The style sheet is the ONLY thing that carries a "
        f"character's look from one section to the next, so it must be "
        f"specific enough to survive on its own.\n"
        f"\n"
        f"THEN write the prompts. How they chain matters:\n"
        f"- The FIRST drawing of every section is generated from its text "
        f"alone, so it must be self-contained and establish the whole scene. "
        f"Never begin a section's first prompt with a back-reference.\n"
        f"- Every LATER drawing in a section is generated as a continuation "
        f"of the drawing immediately before it, so write it as a change: "
        f"keep the same figure and setting and alter or add exactly one "
        f"thing, referring back explicitly, for example 'the same wolf, now "
        f"stepping toward the firelight'.\n"
        f"- Drawings never chain across a section boundary. Each section is a "
        f"fresh visual start.\n"
        f"\n"
        f"DRAWING CONSTRAINTS:\n"
        f"- The drawings are plain black outline sketches with stick-figure "
        f"people. Describe simple shapes, poses and objects only.\n"
        f"- Never ask for text, letters, numbers or labels in a drawing.\n"
        f"- Colours are solid flat fills inside the outlines. Never ask for "
        f"shading, gradients, texture or photographic detail.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES FOR IMAGE PROMPTS:\n"
        f"- All prompts must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Do not include prompts that could generate images of weapons, "
        f"gore, or harmful content\n"
        f"- Avoid prompts that could create images with nudity, sexual "
        f"content, or adult themes\n"
        f"\n"
        f"COPYRIGHT AND INTELLECTUAL PROPERTY GUIDELINES:\n"
        f"- NEVER include copyrighted characters, brands, or intellectual "
        f"property in prompts\n"
        f"- Use generic descriptions such as 'wise green alien mentor' "
        f"instead of a specific character name\n"
        f"- Avoid famous logos, brand names, or trademarked symbols"
    )


@with_retry
def _request_prompts(client, message: str) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": PROMPTS_SYSTEM_MESSAGE},
            {"role": "user", "content": message},
        ],
        temperature=config.TEXT_TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "storyboard_prompts",
                "strict": True,
                "schema": PROMPTS_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def _decode_sections(content: str | None) -> tuple[str, list[list[str]]]:
    """Pull the style sheet and per-section prompt lists out of a response."""
    try:
        payload = json.loads(content or "")
    except json.JSONDecodeError as exc:
        raise PromptGenerationError(f"prompt output was not valid JSON: {exc}") from exc

    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        raise PromptGenerationError("prompt output has no 'sections' list")

    prompt_lists: list[list[str]] = []
    for entry in raw_sections:
        raw = entry.get("prompts") if isinstance(entry, dict) else None
        prompt_lists.append(
            [p.strip() for p in raw if isinstance(p, str) and p.strip()]
            if isinstance(raw, list)
            else []
        )
    return str(payload.get("style") or "").strip(), prompt_lists


def _empty_positions(script: Script, prompt_lists: Sequence[Sequence[str]]) -> list[int]:
    """1-based positions of sections that came back with nothing usable.

    A short-but-non-empty section is NOT reported: we set the budget
    ourselves and assembly divides measured audio by the actual shot count,
    so an off-budget section still yields a correct video.
    """
    if len(prompt_lists) != len(script.sections):
        return list(range(1, len(script.sections) + 1))
    return [
        position
        for position, prompts in enumerate(prompt_lists, start=1)
        if not prompts
    ]


def generate_prompts(script: Script, *, client=None) -> Script:
    """Fill `script` with a global style sheet and one prompt per shot.

    Prompt counts that differ from the budget are honoured, not corrected.
    A section that comes back empty triggers exactly one repair call.
    """
    client = client or get_open_ai_client()
    budgets = shot_budgets(script)
    message = build_prompts_message(script, budgets)

    style, prompt_lists = _decode_sections(_request_prompts(client, message))
    missing = _empty_positions(script, prompt_lists)

    if missing:
        listing = ", ".join(str(position) for position in missing)
        repair = (
            f"{message}\n\n"
            f"Your previous answer returned no drawings for section(s) "
            f"{listing}. Return ALL {len(script.sections)} sections in order, "
            f"each with at least one drawing."
        )
        style, prompt_lists = _decode_sections(_request_prompts(client, repair))
        missing = _empty_positions(script, prompt_lists)
        if missing:
            listing = ", ".join(f"section {position}" for position in missing)
            raise PromptGenerationError(
                f"the model returned no drawings for {listing} twice; "
                f"refusing to generate a section with no visuals"
            )

    filled = tuple(
        replace(section, prompts=tuple(prompts))
        for section, prompts in zip(script.sections, prompt_lists)
    )
    return replace(script, style=style, sections=filled)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_generate_prompts.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/generate_prompts tests/test_generate_prompts.py
git commit -m "feat: generate a style sheet and image prompts from a whole script"
```

---

### Task 6: Chained image generation

The heart of the change. Each section is one job that walks its shots sequentially; sections run in parallel. `reference` tracks the last shot that *succeeded*, so a mid-chain failure costs one frame rather than the section's tail.

**Files:**
- Modify: `scripts/ai/generate_images/generate_images.py`
- Test: `tests/test_generate_images.py`

**Interfaces:**
- Consumes: `models.Script`, `utils.paths.section_image_path`, `.utils.styled_prompt`, `.utils.generate_image`, `.utils.generate_image_from_reference`, `utils.openai_support.TaskResult`.
- Produces: `run_section_chain(section_number, section, style, *, client=None, on_shot=None) -> list[TaskResult]`, `section_chain_jobs(script, *, client=None, on_shot=None) -> list[Job]`, `flatten_chain_results(results) -> list[TaskResult]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate_images.py`:

```python
from models import Script, Section
from scripts.ai.generate_images import generate_images as images_module
from scripts.ai.generate_images.generate_images import (
    flatten_chain_results,
    run_section_chain,
    section_chain_jobs,
)
from utils.openai_support import TaskResult
from utils.paths import section_image_path


class RecordingImages:
    """Stands in for the two image entry points, recording every call."""

    def __init__(self, fail_on=()):
        self.fresh = []          # prompts generated from text alone
        self.continued = []      # (prompt, reference) pairs
        self.fail_on = set(fail_on)  # 1-based shot numbers that raise
        self._shot = 0

    def generate_image(self, prompt, destination, *, client=None):
        self._shot += 1
        if self._shot in self.fail_on:
            raise RuntimeError(f"shot {self._shot} failed")
        self.fresh.append(prompt)
        return destination

    def generate_image_from_reference(self, prompt, reference, destination, *, client=None):
        self._shot += 1
        if self._shot in self.fail_on:
            raise RuntimeError(f"shot {self._shot} failed")
        self.continued.append((prompt, reference))
        return destination


def install(monkeypatch, recorder):
    monkeypatch.setattr(images_module, "generate_image", recorder.generate_image)
    monkeypatch.setattr(
        images_module,
        "generate_image_from_reference",
        recorder.generate_image_from_reference,
    )


def build_section(prompts=("p1", "p2", "p3")):
    return Section("HOOK", "Narration.", tuple(prompts))


def test_first_shot_is_generated_from_text_alone(monkeypatch):
    recorder = RecordingImages()
    install(monkeypatch, recorder)
    run_section_chain(1, build_section(), "STYLE SHEET")
    assert len(recorder.fresh) == 1
    assert "STYLE SHEET" in recorder.fresh[0]
    assert "p1" in recorder.fresh[0]


def test_later_shots_continue_the_previous_shot(monkeypatch):
    recorder = RecordingImages()
    install(monkeypatch, recorder)
    run_section_chain(1, build_section(), "STYLE SHEET")
    assert len(recorder.continued) == 2
    assert recorder.continued[0][1] == section_image_path(1, 1)
    assert recorder.continued[1][1] == section_image_path(1, 2)


def test_a_mid_chain_failure_continues_from_the_last_success(monkeypatch):
    recorder = RecordingImages(fail_on={2})
    install(monkeypatch, recorder)
    results = run_section_chain(1, build_section(), "STYLE")
    assert [r.ok for r in results] == [True, False, True]
    # Shot 3 continues from shot 1, not from the missing shot 2.
    assert recorder.continued[-1][1] == section_image_path(1, 1)


def test_a_failed_first_shot_makes_the_next_shot_fresh(monkeypatch):
    recorder = RecordingImages(fail_on={1})
    install(monkeypatch, recorder)
    results = run_section_chain(1, build_section(), "STYLE")
    assert results[0].ok is False
    # Nothing has succeeded yet, so shot 2 is generated from text.
    assert len(recorder.fresh) == 1
    assert "p2" in recorder.fresh[0]


def test_reports_one_result_per_shot_with_a_readable_label(monkeypatch):
    install(monkeypatch, RecordingImages())
    results = run_section_chain(2, build_section(), "STYLE")
    assert [r.label for r in results] == [
        "image section 2 shot 1",
        "image section 2 shot 2",
        "image section 2 shot 3",
    ]


def test_on_shot_fires_once_per_shot_as_it_completes(monkeypatch):
    install(monkeypatch, RecordingImages())
    seen = []
    run_section_chain(1, build_section(), "STYLE", on_shot=seen.append)
    assert len(seen) == 3
    assert all(isinstance(entry, TaskResult) for entry in seen)


def test_one_job_per_section_with_prompts():
    script = Script(
        topic="t",
        title="T",
        style="STYLE",
        sections=(build_section(), Section("SETUP", "N.", ()), build_section(("a",))),
    )
    jobs = section_chain_jobs(script)
    # The promptless middle section contributes no job.
    assert [label for label, _ in jobs] == ["images section 1", "images section 3"]


def test_flatten_unwraps_per_section_result_lists():
    inner = [TaskResult("shot 1"), TaskResult("shot 2")]
    outer = [TaskResult("images section 1", value=inner)]
    assert flatten_chain_results(outer) == inner


def test_flatten_keeps_a_failed_chain_job_as_one_result():
    failed = TaskResult("images section 1", error=RuntimeError("pool died"))
    assert flatten_chain_results([failed]) == [failed]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_generate_images.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_section_chain'`

- [ ] **Step 3: Write the implementation**

Append to `scripts/ai/generate_images/generate_images.py`, keeping `anchor_jobs`/`followup_jobs`/`generate_images` in place until Task 11:

```python
def run_section_chain(
    section_number: int,
    section: Section,
    style: str,
    *,
    client=None,
    on_shot: Callable[[TaskResult], None] | None = None,
) -> list[TaskResult]:
    """Draw one section's shots in order, each continuing the one before.

    `reference` holds the last shot that actually succeeded, so a failure in
    the middle costs one frame and one continuity beat rather than every
    remaining shot in the section. Before anything has succeeded — including
    after a failed first shot — the next shot is drawn from text alone.

    Returns one `TaskResult` per shot. The caller flattens these with
    `flatten_chain_results`; `on_shot` fires as each one lands so a progress
    display still ticks per image rather than per section.
    """
    results: list[TaskResult] = []
    reference: Path | None = None

    for shot_number, prompt in enumerate(section.prompts, start=1):
        destination = section_image_path(section_number, shot_number)
        label = f"image section {section_number} shot {shot_number}"
        styled = styled_prompt(style, prompt)
        try:
            if reference is None:
                generate_image(styled, destination, client=client)
            else:
                generate_image_from_reference(
                    styled, reference, destination, client=client
                )
            result = TaskResult(label, value=destination)
            reference = destination
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            result = TaskResult(label, error=exc)

        results.append(result)
        if on_shot is not None:
            on_shot(result)

    return results


def section_chain_jobs(
    script: Script,
    *,
    client=None,
    on_shot: Callable[[TaskResult], None] | None = None,
) -> list[Job]:
    """One job per section. Sections are independent, so these run in parallel.

    Parallelism is bounded by section count rather than image count; wall time
    is roughly the longest single chain.
    """
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        if not section.prompts:
            continue
        jobs.append(
            (
                f"images section {section_number}",
                lambda n=section_number, s=section: run_section_chain(
                    n, s, script.style, client=client, on_shot=on_shot
                ),
            )
        )
    return jobs


def flatten_chain_results(results: Sequence[TaskResult]) -> list[TaskResult]:
    """Unwrap per-section result lists into one result per shot.

    A chain job that failed outright — rather than returning per-shot results —
    is kept as-is so the failure is still reported.
    """
    flat: list[TaskResult] = []
    for result in results:
        if result.ok and isinstance(result.value, list):
            flat.extend(result.value)
        else:
            flat.append(result)
    return flat
```

Extend the module's imports:

```python
from pathlib import Path
from typing import Callable, Sequence

from models import Item, Script, Section
from utils.paths import image_path, section_image_path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_generate_images.py -v`
Expected: PASS, including the pre-existing anchor/follow-up tests.

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/ai/generate_images/generate_images.py tests/test_generate_images.py
git commit -m "feat: draw each section as a chain that resets at the boundary"
```

---

### Task 7: Per-section narration

One mp3 per section — the unit that makes assembly-time sync measurable.

**Files:**
- Modify: `scripts/ai/generate_audios/utils.py`, `scripts/ai/generate_audios/generate_audio.py`
- Test: `tests/test_generate_audio.py`

**Interfaces:**
- Consumes: `models.Script`, `models.Section`, `utils.paths.section_audio_path`.
- Produces: `generate_audio_for_section(section, destination, *, client=None) -> Path`, `section_audio_jobs(script, *, client=None) -> list[Job]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate_audio.py`:

```python
from models import Script, Section
from scripts.ai.generate_audios.generate_audio import section_audio_jobs
from scripts.ai.generate_audios.utils import generate_audio_for_section


def build_script():
    return Script(
        topic="wolves",
        title="T",
        sections=(
            Section("HOOK", "Your dog's ancestor could have killed you."),
            Section("SETUP", "Grey wolves found our camps."),
        ),
    )


def test_narrates_the_section_text_only(tmp_path):
    """The label is a production note, not spoken words."""
    client, speech = fake_client()
    section = Section("HOOK", "Your dog's ancestor could have killed you.")
    generate_audio_for_section(section, tmp_path / "section_01.mp3", client=client)
    assert speech.calls[0]["input"] == "Your dog's ancestor could have killed you."
    assert "HOOK" not in speech.calls[0]["input"]


def test_writes_the_audio_file(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "section_01.mp3"
    generate_audio_for_section(Section("HOOK", "Line."), destination, client=client)
    assert destination.read_bytes() == MP3_BYTES


def test_raises_when_the_api_returns_nothing(tmp_path):
    client, _ = fake_client(payload=b"")
    with pytest.raises(ValueError, match="No audio data"):
        generate_audio_for_section(
            Section("HOOK", "Line."), tmp_path / "s.mp3", client=client
        )


def test_one_job_per_section_targeting_its_own_file():
    jobs = section_audio_jobs(build_script())
    assert [label for label, _ in jobs] == ["audio section 1", "audio section 2"]
```

These reuse the `FakeSpeech` class, the `fake_client()` helper and the `MP3_BYTES`
constant already at the top of `tests/test_generate_audio.py`. Do not add a new
fake.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_generate_audio.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_audio_for_section'`

- [ ] **Step 3: Write the implementation**

Append to `scripts/ai/generate_audios/utils.py`:

```python
@with_retry
def generate_audio_for_section(
    section: Section, destination: Path, *, client=None
) -> Path:
    """Narrate one section's prose into `destination`.

    The label is a production note, not spoken words — only `narration` is
    sent, which is also what makes the measured duration match the text the
    shots were counted from.
    """
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.audio.speech.create(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        instructions=config.TTS_INSTRUCTIONS,
        input=section.narration,
    )

    payload = b"".join(response.iter_bytes())
    if not payload:
        raise ValueError(
            f"No audio data returned from API for section: {section.label!r}"
        )

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)

    return destination
```

Update that file's imports to `from models import Item, Section`.

Append to `scripts/ai/generate_audios/generate_audio.py`:

```python
def section_audio_jobs(script: Script, *, client=None) -> list[Job]:
    """One narration job per section. All independent, all parallelizable."""
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        destination = section_audio_path(section_number)
        jobs.append(
            (
                f"audio section {section_number}",
                lambda s=section, d=destination: generate_audio_for_section(
                    s, d, client=client
                ),
            )
        )
    return jobs
```

Update that file's imports:

```python
from models import Item, Script
from utils.paths import audio_path, section_audio_path

from .utils import generate_audio_for_item, generate_audio_for_section
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_generate_audio.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/ai/generate_audios tests/test_generate_audio.py
git commit -m "feat: narrate one audio file per script section"
```

---

### Task 8: Frame composition without titles

Same blurred backdrop, no text, image centred. `wrap_text`, `load_title_font`, `FONT_CANDIDATES` and `TitleFontNotFoundError` do not move across — they exist only to draw titles and die with them in Task 11.

**Files:**
- Create: `scripts/non_ai/compose_frames/__init__.py`, `scripts/non_ai/compose_frames/utils.py`, `scripts/non_ai/compose_frames/compose_frames.py`
- Test: `tests/test_compose.py`

**Interfaces:**
- Consumes: `utils.paths.section_image_path`, `utils.paths.composed_image_path`, `models.Script`.
- Produces: `scaled_height(source_width, source_height, target_width) -> int`, `blurred_background(source, size) -> Image`, `compose_frame(source_path, destination) -> Path`, `compose_jobs(script) -> list[Job]`, `compose_frames_for_script(script, *, on_done=None) -> list[TaskResult]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_compose.py`:

```python
import pytest
from PIL import Image

import config
from models import Script, Section
from scripts.non_ai.compose_frames.compose_frames import compose_jobs
from scripts.non_ai.compose_frames.utils import (
    blurred_background,
    compose_frame,
    scaled_height,
)


def write_source(path, size=(1024, 1024), colour=(200, 30, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    return path


def build_script():
    return Script(
        topic="t",
        title="T",
        sections=(
            Section("HOOK", "N.", ("p1", "p2")),
            Section("SETUP", "N.", ("p1",)),
        ),
    )


def test_scaled_height_preserves_aspect_ratio():
    assert scaled_height(1000, 500, 1080) == 540


def test_scaled_height_rejects_a_degenerate_source():
    with pytest.raises(ValueError, match="non-positive"):
        scaled_height(0, 100, 1080)


def test_composed_frame_is_the_full_shorts_canvas(tmp_path):
    source = write_source(tmp_path / "in.png")
    destination = compose_frame(source, tmp_path / "out.png")
    with Image.open(destination) as composed:
        assert composed.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_image_is_centred_vertically(tmp_path):
    """A square source on a 9:16 canvas leaves equal bands above and below."""
    source = write_source(tmp_path / "in.png", size=(1024, 1024))
    destination = compose_frame(source, tmp_path / "out.png")
    foreground_height = scaled_height(1024, 1024, config.VIDEO_WIDTH)
    expected_top = (config.VIDEO_HEIGHT - foreground_height) // 2
    with Image.open(destination) as composed:
        pixels = composed.convert("RGB")
        # The source colour starts at the top of the centred foreground.
        assert pixels.getpixel((config.VIDEO_WIDTH // 2, expected_top + 5)) == (200, 30, 30)
        # And the band above it is backdrop, not source.
        assert pixels.getpixel((config.VIDEO_WIDTH // 2, expected_top - 20)) != (200, 30, 30)


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Source image not found"):
        compose_frame(tmp_path / "absent.png", tmp_path / "out.png")


def test_blurred_background_fills_the_canvas(tmp_path):
    with Image.open(write_source(tmp_path / "in.png")) as source:
        background = blurred_background(source, (config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
    assert background.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_one_job_per_shot_across_every_section():
    labels = [label for label, _ in compose_jobs(build_script())]
    assert labels == [
        "compose section 1 shot 1",
        "compose section 1 shot 2",
        "compose section 2 shot 1",
    ]


def test_composition_uses_no_font(tmp_path, monkeypatch):
    """Regression guard: the title path is gone, so no font is ever loaded."""
    import PIL.ImageFont

    def explode(*args, **kwargs):
        raise AssertionError("compose_frame must not load a font")

    monkeypatch.setattr(PIL.ImageFont, "truetype", explode)
    source = write_source(tmp_path / "in.png")
    compose_frame(source, tmp_path / "out.png")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_compose.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.non_ai.compose_frames'`

- [ ] **Step 3: Create the package**

```bash
mkdir -p scripts/non_ai/compose_frames
touch scripts/non_ai/compose_frames/__init__.py
```

- [ ] **Step 4: Write the single-frame composition**

Create `scripts/non_ai/compose_frames/utils.py`:

```python
"""Compose a source image onto a 1080x1920 Shorts frame.

No text. The narration carries the message, and a static title burned across
eighty-five seconds of continuous video reads as clutter.
"""

from pathlib import Path

from PIL import Image, ImageFilter

import config


def scaled_height(source_width: int, source_height: int, target_width: int) -> int:
    """Height that preserves the aspect ratio when scaling to `target_width`."""
    if source_height <= 0 or source_width <= 0:
        raise ValueError(
            f"Source image has a non-positive dimension: "
            f"{source_width}x{source_height}"
        )
    return round(target_width * source_height / source_width)


def blurred_background(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Build the blurred, lightened backdrop.

    Blurring at 1/N scale and upscaling gives a visually identical result to a
    full-resolution blur at this radius, for roughly 1/N^2 of the work.
    """
    width, height = size
    factor = config.BLUR_DOWNSCALE_FACTOR

    small_size = (max(1, width // factor), max(1, height // factor))
    small = source.convert("RGB").resize(small_size, Image.Resampling.BILINEAR)
    small = small.filter(
        ImageFilter.GaussianBlur(radius=config.BACKGROUND_BLUR_RADIUS / factor)
    )
    background = small.resize(size, Image.Resampling.BILINEAR)

    overlay = Image.new("RGBA", size, (255, 255, 255, config.BACKGROUND_OVERLAY_ALPHA))
    return Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")


def compose_frame(source_path: Path, destination: Path) -> Path:
    """Render `source_path` centred on its own blurred backdrop."""
    source_path = Path(source_path)
    destination = Path(destination)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas_size = (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)

    with Image.open(source_path) as opened:
        source = opened.convert("RGB")
        foreground_height = scaled_height(
            source.width, source.height, config.VIDEO_WIDTH
        )
        foreground = source.resize(
            (config.VIDEO_WIDTH, foreground_height), Image.Resampling.LANCZOS
        )
        canvas = blurred_background(source, canvas_size)

    # Centred, with no reserved band: nothing sits below the image any more.
    foreground_top = (config.VIDEO_HEIGHT - foreground_height) // 2
    canvas.paste(foreground, (0, foreground_top))

    canvas.save(destination)
    return destination
```

- [ ] **Step 5: Write the job fan-out**

Create `scripts/non_ai/compose_frames/compose_frames.py`:

```python
"""Render a Shorts frame for every generated shot."""

from concurrent.futures import ThreadPoolExecutor

import config
from models import Script
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import composed_image_path, section_image_path

from .utils import compose_frame


def compose_jobs(script: Script) -> list[Job]:
    jobs: list[Job] = []
    for section_number, section in enumerate(script.sections, start=1):
        for shot_number in range(1, len(section.prompts) + 1):
            source = section_image_path(section_number, shot_number)
            destination = composed_image_path(section_number, shot_number)
            jobs.append(
                (
                    f"compose section {section_number} shot {shot_number}",
                    lambda s=source, d=destination: compose_frame(s, d),
                )
            )
    return jobs


def compose_frames_for_script(script: Script, *, on_done=None) -> list[TaskResult]:
    """Render every frame. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, compose_jobs(script), on_done=on_done)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_compose.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 7: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scripts/non_ai/compose_frames tests/test_compose.py
git commit -m "feat: compose untitled Shorts frames with the image centred"
```

---

### Task 9: Video assembly from sections

Silence belongs only at the two ends of the whole video. Assembly returns the measured per-section durations so the archive can write them back without reopening the audio.

**Files:**
- Modify: `scripts/non_ai/generate_video_short/utils.py`, `scripts/non_ai/generate_video_short/generate_video_short.py`
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: `models.Script`, `utils.paths.section_audio_path`, `utils.paths.composed_image_path`, existing `segment_bounds`.
- Produces: `build_section_audio(section_number, *, is_first, is_last) -> tuple[CompositeAudioClip, float]`, `build_section_clip(section_number, section, *, is_first, is_last)`, `generate_video_from_script(script) -> tuple[Path, list[float]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_video.py`:

```python
from models import Script, Section
from scripts.non_ai.generate_video_short import utils as video_utils
from scripts.non_ai.generate_video_short.utils import segment_bounds


def test_segment_bounds_splits_a_section_evenly():
    bounds = segment_bounds(10.0, 4)
    assert [round(duration, 6) for _, duration in bounds] == [2.5, 2.5, 2.5, 2.5]
    assert bounds[0][0] == 0.0
    assert round(bounds[-1][0], 6) == 7.5


def test_segment_bounds_rejects_a_section_with_no_shots():
    with pytest.raises(ValueError, match="at least one image"):
        segment_bounds(10.0, 0)


class FakeVoice:
    """Stands in for an AudioFileClip with a known duration."""

    def __init__(self, duration):
        self.duration = duration

    def set_start(self, start):
        self.start = start
        return self


def test_only_the_first_section_gets_intro_silence(monkeypatch):
    monkeypatch.setattr(video_utils, "AudioFileClip", lambda path: FakeVoice(10.0))
    monkeypatch.setattr(
        video_utils,
        "CompositeAudioClip",
        lambda clips: SimpleNamespace(set_duration=lambda d: SimpleNamespace(duration=d)),
    )

    _, first = video_utils.build_section_audio(1, is_first=True, is_last=False)
    _, middle = video_utils.build_section_audio(2, is_first=False, is_last=False)
    _, last = video_utils.build_section_audio(3, is_first=False, is_last=True)

    assert first == 10.0 + config.INTRO_SILENCE_SECONDS
    assert middle == 10.0
    assert last == 10.0 + config.OUTRO_SILENCE_SECONDS


def test_a_single_section_gets_both_silences(monkeypatch):
    monkeypatch.setattr(video_utils, "AudioFileClip", lambda path: FakeVoice(10.0))
    monkeypatch.setattr(
        video_utils,
        "CompositeAudioClip",
        lambda clips: SimpleNamespace(set_duration=lambda d: SimpleNamespace(duration=d)),
    )
    _, total = video_utils.build_section_audio(1, is_first=True, is_last=True)
    assert total == (
        10.0 + config.INTRO_SILENCE_SECONDS + config.OUTRO_SILENCE_SECONDS
    )
```

Import `SimpleNamespace` and `config` at the top of the file if they are not already imported.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_video.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_section_audio'`

- [ ] **Step 3: Write the assembly helpers**

Append to `scripts/non_ai/generate_video_short/utils.py`:

```python
def build_section_audio(
    section_number: int, *, is_first: bool, is_last: bool
) -> tuple[CompositeAudioClip, float]:
    """One section's narration, padded only where the video actually ends.

    Padding every section — as the per-item version did — puts a silent gap at
    every interior boundary, which is what makes a concatenation sound like
    separate clips rather than one continuous video.
    """
    voice = AudioFileClip(str(section_audio_path(section_number)))
    lead = config.INTRO_SILENCE_SECONDS if is_first else 0.0
    tail = config.OUTRO_SILENCE_SECONDS if is_last else 0.0
    total_duration = lead + voice.duration + tail
    padded = CompositeAudioClip([voice.set_start(lead)]).set_duration(total_duration)
    return padded, total_duration


def build_section_clip(
    section_number: int, section: Section, *, is_first: bool, is_last: bool
):
    """One section: its shots held in equal turns over its narration."""
    audio, total_duration = build_section_audio(
        section_number, is_first=is_first, is_last=is_last
    )

    layers = [build_background_clip(total_duration)]
    for shot_number, (start, duration) in enumerate(
        segment_bounds(total_duration, len(section.prompts)), start=1
    ):
        layers.append(
            build_image_clip(
                composed_image_path(section_number, shot_number), duration, start
            )
        )

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
```

Update that file's imports:

```python
from models import Item, Section
from utils.paths import audio_path, composed_image_path, section_audio_path, titled_image_path
```

Also relax `segment_bounds`'s error message so it reads correctly for sections — change `"Need at least one image per item, got 0"` to `"Need at least one image per section, got 0"`, and update the existing assertion in `tests/test_video.py` that matches on that string.

- [ ] **Step 4: Write the top-level renderer**

Append to `scripts/non_ai/generate_video_short/generate_video_short.py`:

```python
def generate_video_from_script(script: Script) -> tuple[Path, list[float]]:
    """Render the script into one 1080x1920 video.

    Returns the output path and the measured duration of each section, so the
    archive can write real timings into `script.json` without reopening every
    mp3.
    """
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = video_output_path()

    last = len(script.sections)
    clips = [
        build_section_clip(
            section_number,
            section,
            is_first=section_number == 1,
            is_last=section_number == last,
        )
        for section_number, section in enumerate(script.sections, start=1)
    ]
    durations = [clip.duration for clip in clips]

    final_clip = concatenate_videoclips(clips)
    try:
        final_clip.write_videofile(
            str(output_path),
            fps=config.VIDEO_FPS,
            codec=config.VIDEO_CODEC,
            audio_codec=config.VIDEO_AUDIO_CODEC,
            preset=config.VIDEO_PRESET,
            threads=os.cpu_count() or 4,
        )
    finally:
        final_clip.close()
        for clip in clips:
            clip.close()

    return output_path, durations
```

Update that file's imports to bring in `Script` and `build_section_clip`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_video.py -v`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/non_ai/generate_video_short tests/test_video.py
git commit -m "feat: assemble one continuous video from script sections"
```

---

### Task 10: Archiving with measured timings

**Files:**
- Modify: `scripts/non_ai/save_to_generated_data/save_to_generated_data.py`, `utils/paths.py`
- Test: `tests/test_archive.py`

**Interfaces:**
- Consumes: `models.with_durations`, `models.save_script`, `utils.paths.COMPOSED_IMAGE_OUTPUT_DIR`.
- Produces: `ARCHIVED_SCRIPT_FILENAME = "script.json"` in `utils/paths.py`; `save_script_to_generated_data(script, durations) -> Path`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archive.py`:

```python
import json

from models import Script, Section, load_script
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_script_to_generated_data,
)
from utils.paths import (
    ARCHIVED_SCRIPT_FILENAME,
    COMPOSED_IMAGE_OUTPUT_DIR,
    GENERATED_DATA_ROOT,
)


def build_script(topic="how dogs evolved"):
    return Script(
        topic=topic,
        title="Wolves Domesticated Themselves",
        style="A grey-blue wolf.",
        sections=(
            Section("HOOK", "One line.", ("p1", "p2")),
            Section("SETUP", "Another line.", ("p1",)),
        ),
    )


def test_archives_under_the_topic_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    assert folder == GENERATED_DATA_ROOT / "how_dogs_evolved"
    assert (folder / ARCHIVED_SCRIPT_FILENAME).is_file()


def test_writes_measured_timings_over_the_estimates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    archived = load_script(folder / ARCHIVED_SCRIPT_FILENAME)
    assert (archived.sections[0].start, archived.sections[0].end) == (0.0, 4.0)
    assert (archived.sections[1].start, archived.sections[1].end) == (4.0, 10.0)


def test_copies_composed_frames_not_titled_ones(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    COMPOSED_IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMPOSED_IMAGE_OUTPUT_DIR / "composed_section_01_shot_01.png").write_bytes(b"png")
    folder = save_script_to_generated_data(build_script(), [4.0, 6.0])
    assert (folder / "composed_images" / "composed_section_01_shot_01.png").is_file()


def test_falls_back_to_a_timestamp_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = save_script_to_generated_data(build_script(topic="!!!"), [4.0, 6.0])
    assert folder.name != "untitled"
    assert folder.name.isdigit() or "_" in folder.name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_archive.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_script_to_generated_data'`

- [ ] **Step 3: Add the archive filename constant**

In `utils/paths.py`, beside `ARCHIVED_LIST_FILENAME`:

```python
ARCHIVED_SCRIPT_FILENAME = "script.json"
```

- [ ] **Step 4: Write the implementation**

Append to `scripts/non_ai/save_to_generated_data/save_to_generated_data.py`:

```python
def save_script_to_generated_data(
    script: Script, durations: Sequence[float]
) -> Path:
    """Copy this run's script, audio, images, frames and video into an archive.

    `durations` are the measured section lengths returned by assembly; they
    replace the estimates in the saved `script.json`, which is the first point
    at which every section's real runtime is known.

    Must run *after* the video is rendered, or the archive has no video in it.
    """
    slug = slugify(script.topic)
    if slug == "untitled":
        slug = datetime.now().strftime("%Y%m%d_%H%M%S")

    folder = GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)

    save_script(
        with_durations(script, durations), folder / ARCHIVED_SCRIPT_FILENAME
    )

    audio_count = _copy_tree(AUDIO_OUTPUT_DIR, folder / "audio", ".mp3")
    image_count = _copy_tree(IMAGE_OUTPUT_DIR, folder / "images", ".png")
    composed_count = _copy_tree(
        COMPOSED_IMAGE_OUTPUT_DIR, folder / "composed_images", ".png"
    )

    video = video_output_path()
    if video.exists():
        shutil.copy2(video, folder / VIDEO_FILENAME)

    print(
        f"\nArchived to {folder}: {audio_count} audio, {image_count} images, "
        f"{composed_count} composed frames"
        + (", 1 video" if video.exists() else ", no video")
    )
    return folder
```

Extend that file's imports:

```python
from models import Item, Script, save_items, save_script, with_durations
from utils.paths import (
    ARCHIVED_LIST_FILENAME,
    ARCHIVED_SCRIPT_FILENAME,
    AUDIO_OUTPUT_DIR,
    COMPOSED_IMAGE_OUTPUT_DIR,
    GENERATED_DATA_ROOT,
    IMAGE_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    VIDEO_FILENAME,
    slugify,
    video_output_path,
)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_archive.py -v`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/non_ai/save_to_generated_data utils/paths.py tests/test_archive.py
git commit -m "feat: archive scripts with measured section timings"
```

---

### Task 11: Cut over the pipeline and CLI, delete the list path

The suite goes red in the middle of this task and green at the end. That is expected and is why the deletion lives here rather than spread across tasks: `Item` cannot be removed until nothing imports it.

**Files:**
- Modify: `pipeline.py`, `main.py`, `models.py`, `config.py`, `utils/paths.py`, `scripts/ai/generate_images/generate_images.py`, `scripts/ai/generate_audios/*`, `scripts/non_ai/generate_video_short/*`, `scripts/non_ai/save_to_generated_data/save_to_generated_data.py`
- Delete: `scripts/ai/generate_list/`, `scripts/non_ai/create_titled_images_short/`, `tests/test_generate_list.py`, `tests/test_titled_images.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything built in Tasks 1–10.
- Produces: `pipeline.TOTAL_STAGES = 6`, `generate_script_stage(topic, target_seconds, *, client=None, log=print) -> Script`, `generate_prompts_stage(script, *, client=None, log=print) -> Script`, `generate_media_stage(script, *, client=None, log=print, on_asset=None)`, `compose_stage(script, *, log=print, on_asset=None)`, `render_video_stage(script, *, log=print) -> tuple[Path, list[float]]`, `archive_stage(script, durations, *, log=print) -> Path`, `media_job_total(script) -> int`, `compose_job_total(script) -> int`, `run_pipeline(topic, target_seconds=None, *, client=None) -> Path`.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_pipeline.py` with:

```python
from pathlib import Path

import pytest

import pipeline
from models import Script, Section
from utils.openai_support import TaskResult


def build_script(prompts_per_section=(2, 3)):
    return Script(
        topic="wolves",
        title="T",
        style="A grey-blue wolf.",
        sections=tuple(
            Section(f"S{i}", f"Narration {i}.", tuple(f"p{j}" for j in range(n)))
            for i, n in enumerate(prompts_per_section, start=1)
        ),
    )


def test_total_stages_is_six():
    assert pipeline.TOTAL_STAGES == 6


def test_media_job_total_counts_one_audio_per_section_plus_every_shot():
    assert pipeline.media_job_total(build_script((2, 3))) == 2 + 5


def test_compose_job_total_counts_every_shot():
    assert pipeline.compose_job_total(build_script((2, 3))) == 5


def test_missing_media_lists_absent_audio_and_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    missing = pipeline.missing_media(build_script((2,)))
    assert len(missing) == 3  # one audio + two shots
    assert all(isinstance(path, Path) for path in missing)


def test_missing_media_ignores_empty_files_as_unusable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from utils.paths import ensure_output_dirs, section_audio_path

    ensure_output_dirs()
    section_audio_path(1).write_bytes(b"")
    assert section_audio_path(1) in pipeline.missing_media(build_script((1,)))


def test_asset_reporter_skips_the_chain_wrapper_result():
    """Chain jobs report per shot via on_shot; the wrapper must not re-report."""
    seen = []
    report = pipeline._asset_reporter(seen.append)
    report(TaskResult("images section 1", value=[TaskResult("shot 1")]))
    report(TaskResult("audio section 1", value=Path("a.mp3")))
    assert [result.label for result in seen] == ["audio section 1"]


def test_asset_reporter_passes_a_failed_chain_job_through():
    seen = []
    report = pipeline._asset_reporter(seen.append)
    report(TaskResult("images section 1", error=RuntimeError("pool died")))
    assert [result.label for result in seen] == ["images section 1"]


def test_asset_reporter_is_none_when_no_callback_given():
    assert pipeline._asset_reporter(None) is None


def test_fail_names_every_missing_file():
    with pytest.raises(pipeline.PipelineError, match="2 required file"):
        pipeline._fail("Media generation", [Path("a.png"), Path("b.mp3")])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL — `AttributeError: module 'pipeline' has no attribute '_asset_reporter'`

- [ ] **Step 3: Rewrite `pipeline.py`**

Replace the whole file with:

```python
"""Stage orchestration for the video generation pipeline.

Each stage is callable on its own so a caller can stop between stages — the
web UI pauses after the prompt stage to let a human edit the script and its
drawings before any paid media is generated. `run_pipeline` composes all six
and is what the CLI uses.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import config
from models import Script, save_script
from scripts.ai.generate_audios.generate_audio import section_audio_jobs
from scripts.ai.generate_images.generate_images import (
    flatten_chain_results,
    section_chain_jobs,
)
from scripts.ai.generate_prompts.generate_prompts import generate_prompts
from scripts.ai.generate_script.generate_script import generate_script
from scripts.non_ai.compose_frames.compose_frames import compose_frames_for_script
from scripts.non_ai.generate_video_short.generate_video_short import (
    generate_video_from_script,
)
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_script_to_generated_data,
)
from utils.openai_support import TaskResult, describe_failures, run_all
from utils.paths import (
    composed_image_path,
    ensure_output_dirs,
    script_path,
    section_audio_path,
    section_image_path,
)

TOTAL_STAGES = 6

Log = Callable[[str], None]
AssetCallback = Callable[[TaskResult], None]


class PipelineError(RuntimeError):
    """A stage produced incomplete output, so the pipeline cannot continue."""


def _unusable(path: Path) -> bool:
    """A file is unusable if it is absent or empty."""
    return not path.exists() or path.stat().st_size == 0


def missing_media(script: Script) -> list[Path]:
    """Every expected narration and shot image that is absent or empty."""
    missing: list[Path] = []
    for section_number, section in enumerate(script.sections, start=1):
        candidate = section_audio_path(section_number)
        if _unusable(candidate):
            missing.append(candidate)
        for shot_number in range(1, len(section.prompts) + 1):
            candidate = section_image_path(section_number, shot_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def missing_composed_frames(script: Script) -> list[Path]:
    """Every expected composed frame that is absent or empty."""
    missing: list[Path] = []
    for section_number, section in enumerate(script.sections, start=1):
        for shot_number in range(1, len(section.prompts) + 1):
            candidate = composed_image_path(section_number, shot_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def _fail(stage: str, paths: list[Path]) -> None:
    listing = "\n".join(f"  - {path}" for path in paths)
    raise PipelineError(
        f"{stage} did not produce {len(paths)} required file(s):\n{listing}\n"
        f"Fix the underlying errors above and re-run."
    )


def media_job_total(script: Script) -> int:
    """One narration per section plus one image per shot."""
    return len(script.sections) + sum(
        len(section.prompts) for section in script.sections
    )


def compose_job_total(script: Script) -> int:
    """One composed frame per generated shot."""
    return sum(len(section.prompts) for section in script.sections)


def _asset_reporter(on_asset: AssetCallback | None) -> AssetCallback | None:
    """Wrap a progress callback so chain jobs are not double-counted.

    A section chain reports each shot through its own `on_shot` as the shot
    lands. The wrapper result `run_all` produces when that job finishes
    carries the same shots again, so it is dropped — unless the job failed
    outright, in which case it is the only report there will be.
    """
    if on_asset is None:
        return None

    def report(result: TaskResult) -> None:
        if result.ok and isinstance(result.value, list):
            return
        on_asset(result)

    return report


def generate_script_stage(
    topic: str,
    target_seconds: int | None = None,
    *,
    client=None,
    log: Log = print,
) -> Script:
    """Stage 1: write the script and save it to disk."""
    ensure_output_dirs()
    target = config.TARGET_VIDEO_SECONDS if target_seconds is None else target_seconds
    log(f"Writing a {target}-second script for '{topic}'...")
    script = generate_script(topic, target, client=client)
    save_script(script, script_path())
    for section in script.sections:
        log(f"  {section.label}: {section.narration}")
    return script


def generate_prompts_stage(
    script: Script, *, client=None, log: Log = print
) -> Script:
    """Stage 2: design the style sheet and every drawing, then save."""
    log("Designing the drawings...")
    filled = generate_prompts(script, client=client)
    save_script(filled, script_path())
    total = compose_job_total(filled)
    log(f"  {total} drawing(s) across {len(filled.sections)} section(s).")
    return filled


def generate_media_stage(
    script: Script,
    *,
    client=None,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 3: narrate every section and draw every shot, then verify.

    Audio jobs and section chains go into one pool together. There are no
    waves any more: chaining is sequential inside a chain job, so ordering is
    that job's problem rather than the scheduler's.
    """
    ensure_output_dirs()
    total = media_job_total(script)
    log(
        f"Generating {total} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        results = run_all(
            executor,
            section_chain_jobs(script, client=client, on_shot=on_asset)
            + section_audio_jobs(script, client=client),
            on_done=_asset_reporter(on_asset),
        )

    failures = describe_failures(flatten_chain_results(results))
    if failures:
        log(failures)

    missing = missing_media(script)
    if missing:
        _fail("Media generation", missing)


def compose_stage(
    script: Script,
    *,
    log: Log = print,
    on_asset: AssetCallback | None = None,
) -> None:
    """Stage 4: compose each shot onto its blurred backdrop."""
    log("Composing frames...")
    results = compose_frames_for_script(script, on_done=on_asset)

    failures = describe_failures(results)
    if failures:
        log(failures)

    missing = missing_composed_frames(script)
    if missing:
        _fail("Frame composition", missing)


def render_video_stage(
    script: Script, *, log: Log = print
) -> tuple[Path, list[float]]:
    """Stage 5: assemble the frames and narration into the final video."""
    log("Assembling video...")
    return generate_video_from_script(script)


def archive_stage(
    script: Script, durations: list[float], *, log: Log = print
) -> Path:
    """Stage 6: copy the whole run into `generated_data/<topic-slug>/`."""
    log("Archiving...")
    return save_script_to_generated_data(script, durations)


def _banner(step: int) -> Log:
    """A logger that stamps a `[n/6]` banner onto the stage's first line only."""
    pending = [True]

    def log(message: str) -> None:
        if pending[0]:
            pending[0] = False
            print(f"\n[{step}/{TOTAL_STAGES}] {message}")
        else:
            print(message)

    return log


def run_pipeline(
    topic: str, target_seconds: int | None = None, *, client=None
) -> Path:
    """Run every stage end to end and return the path to the finished video."""
    ensure_output_dirs()

    script = generate_script_stage(
        topic, target_seconds, client=client, log=_banner(1)
    )
    script = generate_prompts_stage(script, client=client, log=_banner(2))
    generate_media_stage(script, client=client, log=_banner(3))
    compose_stage(script, log=_banner(4))
    video, durations = render_video_stage(script, log=_banner(5))
    archive_stage(script, durations, log=_banner(6))

    return video
```

- [ ] **Step 4: Rewrite the CLI**

In `main.py`, replace `--items` with `--seconds` and rename the prompt helper:

```python
    parser.add_argument(
        "--seconds",
        type=int,
        help="Target video length in seconds. Prompted for if omitted.",
    )
```

```python
def prompt_for_target_seconds() -> int:
    while True:
        raw = input("Enter the target length in seconds: ").strip()
        try:
            seconds = int(raw)
        except ValueError:
            print(f"'{raw}' is not a whole number. Try again.")
            continue
        if seconds < MIN_TARGET_SECONDS:
            print(f"Please enter at least {MIN_TARGET_SECONDS} seconds.")
            continue
        return seconds
```

And in `main()`:

```python
    topic = args.topic.strip() if args.topic else prompt_for_topic()
    if args.seconds is not None:
        if args.seconds < MIN_TARGET_SECONDS:
            print(
                f"--seconds must be at least {MIN_TARGET_SECONDS}, "
                f"got {args.seconds}",
                file=sys.stderr,
            )
            return 2
        target_seconds = args.seconds
    else:
        target_seconds = prompt_for_target_seconds()

    try:
        video = run_pipeline(topic, target_seconds)
    except (PipelineError, InvalidScriptError, PromptGenerationError) as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        return 1
```

Update `main.py`'s imports:

```python
from models import InvalidScriptError
from pipeline import PipelineError, run_pipeline
from scripts.ai.generate_prompts.generate_prompts import PromptGenerationError
from scripts.ai.generate_script.generate_script import MIN_TARGET_SECONDS
```

- [ ] **Step 5: Delete the old modules and their tests**

```bash
git rm -r scripts/ai/generate_list scripts/non_ai/create_titled_images_short
git rm tests/test_generate_list.py tests/test_titled_images.py
```

- [ ] **Step 6: Strip the dead code from the shared modules**

Remove, in this order:

1. `models.py`: `Item`, `Beat`, `InvalidItemsError`, `parse_items`, `items_to_json`, `save_items`, `load_items`, `_required_text`, `_parse_beats`. Keep `_decode` and `_strip_markdown_fences` — `parse_script` uses them.

   **`_decode` currently raises `InvalidItemsError`**, which this step deletes, and
   `parse_script` wraps the call in a `try/except InvalidItemsError` that rewrites
   the message with `.replace("Model output", "Script")`. Both must go in the same
   edit: change `_decode` to raise `InvalidScriptError` directly with the message
   `f"Script was not valid JSON: {exc}"`, then delete the `try/except` in
   `parse_script` so it calls `_decode(raw)` plainly. Leaving either half behind
   breaks the module at import or leaves dead string surgery on an error message
   no longer produced. `test_parse_script_rejects_non_json` must still pass.
2. `config.py`: `IMAGE_PROMPTS_PER_ITEM`, `SECONDS_PER_FRAME`, `TITLE_FONT_SIZE`, `TITLE_LINE_SPACING`, `TITLE_SIDE_MARGIN`, `TITLE_GAP_BELOW_IMAGE`, `TITLE_COLOR`.
3. `utils/paths.py`: `TITLED_IMAGE_OUTPUT_DIR` (and its entry in `ALL_OUTPUT_DIRS`), `LIST_ITEMS_FILENAME`, `ARCHIVED_LIST_FILENAME`, `image_path`, `audio_path`, `titled_image_path`, `list_items_path`.
4. `scripts/ai/generate_images/generate_images.py`: `anchor_jobs`, `followup_jobs`, `generate_images`.
5. `scripts/ai/generate_audios/`: `generate_audio_for_item`, `audio_jobs`, `generate_audio_for_items`.
6. `scripts/non_ai/generate_video_short/`: `beat_weights`, `build_item_audio`, `build_item_clip`, `generate_video_short`.
7. `scripts/non_ai/save_to_generated_data/`: `save_to_generated_data`.
8. The old-shape tests that exercise all of the above. Without this the suite
   fails at collection, not on assertions. Per file:
   - `tests/test_config.py`: replace the `IMAGE_PROMPTS_PER_ITEM` and
     `SECONDS_PER_FRAME` assertions (lines 16-17) with
     `assert module.TARGET_VIDEO_SECONDS == 85` and
     `assert module.SECONDS_PER_IMAGE == pytest.approx(2.5)`.
   - `tests/test_paths.py`: delete `test_image_path_is_zero_padded`,
     `test_image_path_handles_double_digits`, `test_audio_path_is_zero_padded`,
     `test_titled_image_path_has_short_suffix`, `test_list_items_path`.
   - `tests/test_generate_images.py`: delete the `Beat, Item` import, the
     `anchor_jobs`/`followup_jobs`/`generate_images` imports, the `two_items`
     helper, and every test using them. Keep the Task 6 chain tests and any
     `styled_prompt`/`generate_image` tests that do not mention `Item`.
   - `tests/test_generate_audio.py`: delete the `Item` import, the
     `audio_jobs`/`generate_audio_for_items`/`generate_audio_for_item` imports,
     the `two_items` helper and every test using them. **Keep `MP3_BYTES`, the
     `FakeSpeech` class and the `fake_client` helper** — the Task 7 tests are
     written against them.
   - `tests/test_video.py`: delete the `Beat, Item` import, the `beat_weights`
     import and its two tests. **Rewrite** (do not delete) the
     `@pytest.mark.slow` `test_renders_a_real_video` for the section shape: it
     is the only real moviepy encode in the suite. It should build a `Script`
     with one section, write tiny PNGs to `composed_image_path(1, n)` and an
     mp3 to `section_audio_path(1)`, and call `generate_video_from_script`.
   - `tests/test_archive.py`: delete the `Item, load_items` import, the
     `save_to_generated_data` import, the `one_item` helper, the titled-image
     lines in the `populated_outputs` fixture, and every old test. Keep the
     Task 10 tests.

Then fix every remaining import that referenced a deleted name.

- [ ] **Step 7: Run the whole suite**

Run: `venv/bin/pytest`
Expected: the API tests fail — they still post `num_items` and read `items`. Everything else passes. Task 12 fixes the API. Confirm the failures are confined to `tests/api/` before continuing:

```bash
venv/bin/pytest --ignore=tests/api
```
Expected: PASS.

- [ ] **Step 8: Verify no dead references survive**

```bash
grep -rn "Item\b\|Beat\b\|parse_items\|IMAGE_PROMPTS_PER_ITEM\|SECONDS_PER_FRAME\|titled_image\|TITLE_FONT" \
  --exclude-dir=venv --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=docs .
```
Expected: hits only under `api/` and `frontend/` (fixed in Tasks 12–17).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat!: replace the list pipeline with sectioned scripts"
```

---

### Task 12: The HTTP wire contract and run state machine

**Files:**
- Modify: `api/schemas.py`, `api/runs.py`, `api/routes.py`, `api/config_view.py`, `frontend/src/lib/types.ts`
- Test: `tests/api/test_runs.py`, `tests/api/test_routes.py`, `tests/api/test_config_view.py`, `tests/api/test_end_to_end.py`

**Interfaces:**
- Consumes: `pipeline.*` stages from Task 11, `models.Script`, `models.parse_script`.
- Produces: `SectionPayload{label, narration, prompts, start, end}`, `ScriptPayload{topic, title, style, sections}`, `CreateRunRequest{topic, target_seconds, review_script, overrides}`, `ApproveScriptRequest{script}`, `RunSummaryPayload.target_seconds`, `RunDetailPayload.script`, `RunStore.approve_script(run_id, script)`, statuses `generating_script` / `generating_prompts` / `composing_frames`.

- [ ] **Step 1: Create shared API fixtures**

`tests/api/` has no `conftest.py`; `client` is defined locally in
`test_routes.py` and the stage stubs live in a `stub_stages` helper there.
Both need the new stage names, and the tests below need a `store` fixture that
does not yet exist. Create `tests/api/conftest.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from models import Script, Section


def one_script():
    return Script(
        topic="wolves",
        title="Wolves Domesticated Themselves",
        style="A grey-blue wolf with amber eyes.",
        sections=(
            Section("HOOK", "Your dog's ancestor could have killed you.", ("a", "b")),
            Section("SETUP", "Grey wolves found our camps.", ("c",)),
        ),
    )


@pytest.fixture
def stub_stages(monkeypatch):
    """Stub every stage so route/run tests never call OpenAI or render video.

    Deliberately NOT autouse: `tests/api/test_end_to_end.py` drives the real
    stages with only the OpenAI client faked, and is the suite's only
    full-pipeline coverage. An autouse stub would turn it into a green no-op.
    """
    monkeypatch.setattr(
        "api.runs.pipeline.generate_script_stage",
        lambda topic, target_seconds, client=None, log=print: one_script(),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_prompts_stage",
        lambda script, client=None, log=print: script,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_media_stage",
        lambda script, client=None, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.compose_stage",
        lambda script, log=print, on_asset=None: None,
    )

    def fake_render(script, log=print):
        # A real file, because run_detail only advertises a video_url for a
        # video that actually exists on disk.
        video = Path("outputs/video_output/final_video_short.mp4")
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"video")
        return video, [5.0, 15.0]

    monkeypatch.setattr("api.runs.pipeline.render_video_stage", fake_render)
    monkeypatch.setattr(
        "api.runs.pipeline.archive_stage",
        lambda script, durations, log=print: Path("generated_data/wolves"),
    )


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return create_app()


@pytest.fixture
def client(app, stub_stages):
    """A client whose stages are stubbed. End-to-end tests build their own."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def store(app, client):
    """The same RunStore the app is serving, for wait_for_status."""
    return app.state.run_store
```

Then delete the now-duplicated `client` fixture, `stub_stages` helper and
`one_item` helper from `tests/api/test_routes.py`, and remove its
`from models import Item` import.

- [ ] **Step 2: Write the failing tests**

Replace the run-shape tests in `tests/api/test_runs.py` and add to `tests/api/test_routes.py`:

```python
def test_create_run_takes_target_seconds(client):
    response = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": False},
    )
    assert response.status_code == 201
    assert response.json()["target_seconds"] == 85


def test_create_run_rejects_a_target_below_fifteen(client):
    response = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 5}
    )
    assert response.status_code == 422


def test_create_run_rejects_a_target_above_one_eighty(client):
    response = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 200}
    )
    assert response.status_code == 422


def test_run_detail_exposes_the_script(client):
    created = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 85}
    ).json()
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert "script" in detail
    assert set(detail["script"]) == {"topic", "title", "style", "sections"}


def test_approve_script_accepts_an_edited_script(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    detail = client.get(f"/api/runs/{created['id']}").json()

    script = detail["script"]
    script["sections"][0]["narration"] = "An edited hook."
    script["sections"][0]["prompts"] = ["one prompt only"]

    response = client.post(f"/api/runs/{created['id']}/script", json={"script": script})
    assert response.status_code == 200
    approved = response.json()["script"]
    assert approved["sections"][0]["narration"] == "An edited hook."
    assert approved["sections"][0]["prompts"] == ["one prompt only"]


def test_approve_script_rejects_a_script_with_no_sections(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    response = client.post(
        f"/api/runs/{created['id']}/script",
        json={"script": {"topic": "w", "title": "T", "style": "", "sections": []}},
    )
    assert response.status_code == 400


def test_editing_narration_does_not_recount_prompts(client, store):
    """The review gate never regenerates prompts; the shot list is the user's."""
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    script = client.get(f"/api/runs/{created['id']}").json()["script"]

    before = len(script["sections"][0]["prompts"])
    script["sections"][0]["narration"] = "A much much much longer narration. " * 10
    approved = client.post(
        f"/api/runs/{created['id']}/script", json={"script": script}
    ).json()["script"]
    assert len(approved["sections"][0]["prompts"]) == before


def test_config_no_longer_offers_image_prompts_per_item(client):
    names = [field["name"] for field in client.get("/api/config").json()["overridable"]]
    assert "IMAGE_PROMPTS_PER_ITEM" not in names
    assert "TARGET_VIDEO_SECONDS" in names
```

Then rewrite `tests/api/test_end_to_end.py` for the new shape. It builds its own
`TestClient` and drives the real stages with only the OpenAI client faked, so it
does not use the `client` fixture and must not be stubbed. Four changes:

1. Its fake OpenAI client must now answer **two** chat completions in order —
   the script (call 1), then the prompts (call 2). Replace the single
   `ITEMS_JSON` constant with:

```python
SCRIPT_JSON = json.dumps(
    {
        "title": "Wolves Domesticated Themselves",
        "sections": [
            {"label": "HOOK", "narration": "Your dog's ancestor could have killed you."},
            {"label": "PAYOFF", "narration": "Wolves chose us as much as we chose them."},
        ],
    }
)

PROMPTS_JSON = json.dumps(
    {
        "style": "A lean grey-blue wolf with amber eyes.",
        "sections": [
            {"label": "HOOK", "prompts": ["a snarling wolf", "a goofy dog"]},
            {"label": "PAYOFF", "prompts": ["a wolf and a person side by side"]},
        ],
    }
)
```

   The fake's `chat.completions.create` returns `SCRIPT_JSON` on its first call
   and `PROMPTS_JSON` on every call after — a list popped per call, or a counter.

2. Swap the path imports: `image_path` becomes `section_image_path`,
   `titled_image_path` becomes `composed_image_path`, `audio_path` becomes
   `section_audio_path`, and assertions move from `item_01_prompt_01` names to
   `section_01_shot_01` names.

3. The create-run call posts `target_seconds` (use `15`, the floor, to keep the
   render tiny) instead of `num_items`, and `review_script` instead of
   `review_items`.

4. If it exercises the review gate, it posts to `/api/runs/{id}/script` with a
   `{"script": {...}}` body instead of `/items`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/api -v`
Expected: FAIL — the old `num_items` field and `Item` imports.

- [ ] **Step 4: Rewrite the payloads**

In `api/schemas.py`, replace `BeatPayload`/`ItemPayload` with:

```python
class SectionPayload(BaseModel):
    """One section on the wire.

    `start` and `end` are output-only: they are derived from narration length
    and later from measured audio, so a client that edits them is ignored.
    """

    label: str
    narration: str
    prompts: list[str] = Field(default_factory=list)
    start: float = 0.0
    end: float = 0.0


class ScriptPayload(BaseModel):
    topic: str = ""
    title: str = ""
    style: str = ""
    sections: list[SectionPayload] = Field(default_factory=list)

    @classmethod
    def from_script(cls, script: Script) -> "ScriptPayload":
        return cls(
            topic=script.topic,
            title=script.title,
            style=script.style,
            sections=[
                SectionPayload(
                    label=section.label,
                    narration=section.narration,
                    prompts=list(section.prompts),
                    start=section.start,
                    end=section.end,
                )
                for section in script.sections
            ],
        )
```

Then update the run payloads and requests:

```python
class RunSummaryPayload(BaseModel):
    id: str
    topic: str
    target_seconds: int
    status: str
    created_at: str
    finished_at: str | None = None


class RunDetailPayload(RunSummaryPayload):
    review_script: bool
    overrides: dict[str, Any]
    script: ScriptPayload
    assets: list[AssetStatusPayload]
    asset_total: int
    logs: list[str]
    error: str | None = None
    video_url: str | None = None
    archive_slug: str | None = None


class CreateRunRequest(BaseModel):
    topic: str
    target_seconds: int = Field(default=85, ge=15, le=180)
    review_script: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def topic_is_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("topic must not be blank")
        return text


class ApproveScriptRequest(BaseModel):
    script: ScriptPayload
```

Update `run_summary` and `run_detail` to read `run.target_seconds`, `run.review_script`, and `script=ScriptPayload.from_script(run.script)`. Replace `from models import Item` with `from models import Script`.

- [ ] **Step 5: Update the run state machine**

In `api/runs.py`:

- Add the two new statuses beside the existing constants: `STATUS_GENERATING_SCRIPT = "generating_script"`, `STATUS_GENERATING_PROMPTS = "generating_prompts"`.
- On `Run`: `num_items: int` becomes `target_seconds: int`, `review_items: bool` becomes `review_script: bool`, and `items: list[Item]` becomes `script: Script = field(default_factory=lambda: Script(topic="", title=""))`.
- `start(...)` takes `target_seconds` and `review_script`.
- Rename `approve_items` to `approve_script`, taking a `Script`, assigning `run.script`, and saving with `save_script(run.script, script_path())`.
- Rewrite `_execute`'s body to drive the six stages:

```python
                self._check_cancelled(gate)
                self._set_status(run, STATUS_GENERATING_SCRIPT)
                script = pipeline.generate_script_stage(
                    run.topic, run.target_seconds, client=self._client, log=log
                )

                self._check_cancelled(gate)
                self._set_status(run, STATUS_GENERATING_PROMPTS)
                script = pipeline.generate_prompts_stage(
                    script, client=self._client, log=log
                )
                with self._lock:
                    run.script = script

                if run.review_script:
                    self._set_status(run, STATUS_AWAITING_REVIEW)
                    log("Waiting for you to review the script...")
                    gate.review.wait()
                    self._check_cancelled(gate)
                    with self._lock:
                        script = run.script
                    log(f"Continuing with {len(script.sections)} approved section(s).")

                self._check_cancelled(gate)
                self._set_status(run, "generating_media")
                self._begin_asset_stage(run, pipeline.media_job_total(script))
                pipeline.generate_media_stage(
                    script,
                    client=self._client,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "composing_frames")
                self._begin_asset_stage(run, pipeline.compose_job_total(script))
                pipeline.compose_stage(
                    script,
                    log=log,
                    on_asset=lambda result: self._record_asset(run, result),
                )

                self._check_cancelled(gate)
                self._set_status(run, "rendering_video")
                self._begin_asset_stage(run, 0)
                video, durations = pipeline.render_video_stage(script, log=log)
                with self._lock:
                    run.video_path = video

                self._check_cancelled(gate)
                self._set_status(run, "archiving")
                pipeline.archive_stage(script, durations, log=log)
                with self._lock:
                    run.archive_slug = slugify(run.topic)
```

Update the module imports to `from models import Script, save_script` and `from utils.paths import script_path, slugify`.

- [ ] **Step 6: Update the routes**

In `api/routes.py`, change `create_run` to pass `payload.target_seconds` and `review_script=payload.review_script`, and replace the `approve_items` endpoint with:

```python
@router.post("/runs/{run_id}/script", response_model=schemas.RunDetailPayload)
def approve_script(
    run_id: str,
    payload: schemas.ApproveScriptRequest,
    store: RunStore = Depends(get_store),
):
    # Reuse the pipeline's own validation so the UI cannot submit a script the
    # renderer would choke on. Prompt counts are free-form here: the reviewer
    # may legitimately add or remove drawings, and assembly divides measured
    # audio by whatever count each section ends up with.
    try:
        script = parse_script(payload.script.model_dump())
    except InvalidScriptError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        return schemas.run_detail(store.approve_script(run_id, script))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
```

Change the import to `from models import InvalidScriptError, parse_script`.

- [ ] **Step 7: Update the overridable config list**

In `api/config_view.py`, replace the `IMAGE_PROMPTS_PER_ITEM` entry with:

```python
    OverridableField(
        "TARGET_VIDEO_SECONDS",
        "int",
        None,
        "Target spoken length. Section and image counts follow from it.",
    ),
```

and update the `TEXT_MODEL` description to "Writes the script and the drawing prompts."

- [ ] **Step 8: Mirror the contract in TypeScript**

In `frontend/src/lib/types.ts`, replace `Beat`/`ItemPayload` with `Section`/`ScriptPayload`, rename `num_items` to `target_seconds` and `review_items` to `review_script` on `RunSummary`/`RunDetail`/`CreateRunRequest`, replace `items: ItemPayload[]` with `script: ScriptPayload`, and update the status union and stage list:

```typescript
export type RunStatus =
  | "pending"
  | "generating_script"
  | "generating_prompts"
  | "awaiting_review"
  | "generating_media"
  | "composing_frames"
  | "rendering_video"
  | "archiving"
  | "completed"
  | "failed"
  | "cancelled";

export const STAGE_SEQUENCE: readonly { status: RunStatus; label: string }[] = [
  { status: "generating_script", label: "Write script" },
  { status: "generating_prompts", label: "Design drawings" },
  { status: "awaiting_review", label: "Review script" },
  { status: "generating_media", label: "Images & audio" },
  { status: "composing_frames", label: "Compose frames" },
  { status: "rendering_video", label: "Render video" },
  { status: "archiving", label: "Archive" },
];

export interface Section {
  label: string;
  narration: string;
  prompts: string[];
  /** Server-derived timings; sent back but ignored on write. */
  start: number;
  end: number;
}

export interface ScriptPayload {
  topic: string;
  title: string;
  style: string;
  sections: Section[];
}
```

In `frontend/src/lib/api.ts`, replace `approveItems` with:

```typescript
export const approveScript = (runId: string, script: ScriptPayload) =>
  request<RunDetail>(`/runs/${runId}/script`, {
    method: "POST",
    body: JSON.stringify({ script }),
  });
```

and update its import list.

- [ ] **Step 9: Run the backend tests**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add api frontend/src/lib tests/api
git commit -m "feat!: move the HTTP contract from items to sectioned scripts"
```

---

### Task 13: The archive browser API, with legacy fallback

Old `list_items.json` archives stay visible instead of crashing or vanishing.

**Files:**
- Modify: `api/archives.py`, `api/schemas.py`, `frontend/src/lib/types.ts`
- Test: `tests/api/test_archives.py`

**Interfaces:**
- Produces: `ArchiveSummaryPayload{slug, section_count, image_count, audio_count, has_video, legacy, modified_at}`, `ArchiveSectionPayload{label, narration, prompts, image_urls, composed_image_urls, audio_url}`, `ArchiveDetailPayload{slug, title, style, video_url, legacy, sections}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_archives.py`:

```python
import json

from models import Script, Section, save_script
from utils.paths import ARCHIVED_SCRIPT_FILENAME, GENERATED_DATA_ROOT, VIDEO_FILENAME


def write_script_archive(root, slug="wolves"):
    folder = root / GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    save_script(
        Script(
            topic="wolves",
            title="Wolves Domesticated Themselves",
            style="A grey-blue wolf.",
            sections=(Section("HOOK", "One line.", ("p1", "p2"), 0.0, 5.0),),
        ),
        folder / ARCHIVED_SCRIPT_FILENAME,
    )
    (folder / "images").mkdir(exist_ok=True)
    (folder / "images" / "section_01_shot_01.png").write_bytes(b"png")
    (folder / "images" / "section_01_shot_02.png").write_bytes(b"png")
    (folder / "composed_images").mkdir(exist_ok=True)
    (folder / "composed_images" / "composed_section_01_shot_01.png").write_bytes(b"png")
    (folder / "audio").mkdir(exist_ok=True)
    (folder / "audio" / "section_01.mp3").write_bytes(b"mp3")
    (folder / VIDEO_FILENAME).write_bytes(b"mp4")
    return folder


def write_legacy_archive(root, slug="old_run"):
    folder = root / GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "list_items.json").write_text(
        json.dumps([{"title": "Old", "description": "d", "image_prompts": ["p"]}])
    )
    (folder / "images").mkdir(exist_ok=True)
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"png")
    (folder / VIDEO_FILENAME).write_bytes(b"mp4")
    return folder


def test_lists_a_script_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_script_archive(tmp_path)
    from api import archives

    summary = archives.list_archives()[0]
    assert summary["slug"] == "wolves"
    assert summary["section_count"] == 1
    assert summary["image_count"] == 2
    assert summary["legacy"] is False


def test_detail_groups_media_by_section(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_script_archive(tmp_path)
    from api import archives

    detail = archives.archive_detail("wolves")
    assert detail["title"] == "Wolves Domesticated Themselves"
    assert detail["legacy"] is False
    section = detail["sections"][0]
    assert section["label"] == "HOOK"
    assert len(section["image_urls"]) == 2
    assert len(section["composed_image_urls"]) == 1
    assert section["audio_url"].endswith("section_01.mp3")


def test_a_legacy_archive_is_listed_and_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_legacy_archive(tmp_path)
    from api import archives

    summary = archives.list_archives()[0]
    assert summary["legacy"] is True
    assert summary["section_count"] == 0
    assert summary["image_count"] == 1
    assert summary["has_video"] is True


def test_a_legacy_archive_detail_has_no_sections_but_keeps_its_video(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    write_legacy_archive(tmp_path)
    from api import archives

    detail = archives.archive_detail("old_run")
    assert detail["legacy"] is True
    assert detail["sections"] == []
    assert detail["video_url"].endswith(VIDEO_FILENAME)


def test_an_unknown_slug_still_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from api import archives

    with pytest.raises(archives.ArchiveNotFoundError):
        archives.archive_detail("nope")


def test_a_traversal_slug_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from api import archives

    with pytest.raises(archives.ArchiveNotFoundError):
        archives.archive_detail("../etc")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/api/test_archives.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_items'` in `api/archives.py`.

- [ ] **Step 3: Rewrite `api/archives.py`**

Replace the item-shaped helpers with section-shaped ones:

```python
"""Read `generated_data/` into payloads the archive browser can render.

Filenames are the join key: `images/section_04_shot_02.png` belongs to
section 4. Archives written before sectioned scripts carry a `list_items.json`
this module cannot parse; rather than migrating them, they are reported as
`legacy` — slug, media counts and video only. Nothing already generated
disappears from the browser, and no parsing code for the dead format survives.
"""

def _names_for_section(directory: Path, section_number: int, suffix: str) -> list[str]:
    """Every file in `directory` belonging to this section, in shot order."""
    if not directory.is_dir():
        return []
    marker = f"section_{section_number:02d}_"
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix == suffix and marker in entry.name
    )


def _read_script(folder: Path) -> Script | None:
    """The archived script, or None if this is a pre-script archive."""
    listing = folder / ARCHIVED_SCRIPT_FILENAME
    if not listing.is_file():
        return None
    try:
        return load_script(listing)
    except (InvalidScriptError, OSError):
        return None
```

`list_archives` builds each summary with `script = _read_script(folder)`, then:

```python
        summaries.append(
            {
                "slug": folder.name,
                "section_count": len(script.sections) if script else 0,
                "image_count": _count_files(folder / "images", ".png"),
                "audio_count": _count_files(folder / "audio", ".mp3"),
                "has_video": (folder / VIDEO_FILENAME).is_file(),
                "legacy": script is None,
                "modified_at": _modified_at(folder),
            }
        )
```

`archive_detail` becomes:

```python
def archive_detail(slug: str) -> dict[str, Any]:
    """One archive's sections with a media URL for every file that exists."""
    folder = _archive_dir(slug)
    script = _read_script(folder)
    video = folder / VIDEO_FILENAME
    video_url = _url(slug, VIDEO_FILENAME) if video.is_file() else None

    if script is None:
        # A pre-script archive: everything we can still say about it.
        return {
            "slug": slug,
            "title": slug.replace("_", " "),
            "style": "",
            "video_url": video_url,
            "legacy": True,
            "sections": [],
        }

    sections: list[dict[str, Any]] = []
    for section_number, section in enumerate(script.sections, start=1):
        audio_name = f"section_{section_number:02d}.mp3"
        has_audio = (folder / "audio" / audio_name).is_file()
        sections.append(
            {
                "label": section.label,
                "narration": section.narration,
                "start": section.start,
                "end": section.end,
                "prompts": list(section.prompts),
                "image_urls": [
                    _url(slug, "images", name)
                    for name in _names_for_section(
                        folder / "images", section_number, ".png"
                    )
                ],
                "composed_image_urls": [
                    _url(slug, "composed_images", name)
                    for name in _names_for_section(
                        folder / "composed_images", section_number, ".png"
                    )
                ],
                "audio_url": _url(slug, "audio", audio_name) if has_audio else None,
            }
        )

    return {
        "slug": slug,
        "title": script.title,
        "style": script.style,
        "video_url": video_url,
        "legacy": False,
        "sections": sections,
    }
```

Note `archive_detail` no longer raises when the listing is missing — a legacy or media-only folder is a valid archive to browse. `_archive_dir` still raises `ArchiveNotFoundError` for an unknown or traversal slug, which is what the tests assert.

Update the imports to `from models import InvalidScriptError, Script, load_script` and `from utils.paths import ARCHIVED_SCRIPT_FILENAME, GENERATED_DATA_ROOT, VIDEO_FILENAME`.

- [ ] **Step 4: Update the archive payloads**

In `api/schemas.py`:

```python
class ArchiveSummaryPayload(BaseModel):
    slug: str
    section_count: int
    image_count: int
    audio_count: int
    has_video: bool
    legacy: bool = False
    modified_at: str


class ArchiveSectionPayload(BaseModel):
    label: str
    narration: str
    start: float = 0.0
    end: float = 0.0
    prompts: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    composed_image_urls: list[str] = Field(default_factory=list)
    audio_url: str | None = None


class ArchiveDetailPayload(BaseModel):
    slug: str
    title: str = ""
    style: str = ""
    video_url: str | None = None
    legacy: bool = False
    sections: list[ArchiveSectionPayload] = Field(default_factory=list)
```

Mirror all three in `frontend/src/lib/types.ts` as `ArchiveSummary`, `ArchiveSection` and `ArchiveDetail`.

- [ ] **Step 5: Run the tests**

Run: `venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api frontend/src/lib/types.ts tests/api/test_archives.py
git commit -m "feat: browse script archives, keeping old runs as legacy"
```

---

### Task 14: The script review editor

Replaces `ItemEditor`. One global style sheet at the top, then each section as a label, a narration textarea and its prompt rows.

**Files:**
- Create: `frontend/src/components/ScriptEditor.tsx`, `frontend/src/components/ScriptEditor.test.tsx`
- Delete: `frontend/src/components/ItemEditor.tsx`, `frontend/src/components/ItemEditor.test.tsx`

**Interfaces:**
- Consumes: `approveScript` from `@/lib/api`, `ScriptPayload`/`Section` from `@/lib/types`.
- Produces: default export `ScriptEditor({ runId, script, onApproved })`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ScriptEditor.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ScriptEditor from "./ScriptEditor";
import type { ScriptPayload } from "@/lib/types";

const approveScript = vi.fn();
vi.mock("@/lib/api", () => ({
  approveScript: (...args: unknown[]) => approveScript(...args),
}));

const script: ScriptPayload = {
  topic: "wolves",
  title: "Wolves Domesticated Themselves",
  style: "A grey-blue wolf with amber eyes.",
  sections: [
    { label: "HOOK", narration: "Your dog's ancestor could have killed you.", prompts: ["a snarling wolf", "a goofy dog"], start: 0, end: 5 },
    { label: "SETUP", narration: "Wolves found our camps.", prompts: ["wolves near a fire"], start: 5, end: 20 },
  ],
};

beforeEach(() => {
  approveScript.mockReset();
  approveScript.mockResolvedValue({});
});

describe("ScriptEditor", () => {
  it("renders every section with its narration and prompts", () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    expect(screen.getByDisplayValue("HOOK")).toBeInTheDocument();
    expect(screen.getByDisplayValue("SETUP")).toBeInTheDocument();
    expect(screen.getByDisplayValue("a snarling wolf")).toBeInTheDocument();
    expect(screen.getByDisplayValue("wolves near a fire")).toBeInTheDocument();
  });

  it("shows the global style sheet once, not per section", () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    expect(screen.getAllByDisplayValue("A grey-blue wolf with amber eyes.")).toHaveLength(1);
  });

  it("submits edited narration", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.change(screen.getByLabelText("Section 1 narration"), {
      target: { value: "An edited hook." },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].narration).toBe("An edited hook.");
  });

  it("does not change the prompt count when narration is edited", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.change(screen.getByLabelText("Section 1 narration"), {
      target: { value: "A far far far longer narration than before. ".repeat(10) },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toHaveLength(2);
  });

  it("adds a drawing to one section only", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Add drawing to section 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toHaveLength(3);
    expect(submitted.sections[1].prompts).toHaveLength(1);
  });

  it("removes a drawing", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove section 1 drawing 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toEqual(["a goofy dog"]);
  });

  it("removes a whole section", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove section 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections).toHaveLength(1);
    expect(submitted.sections[0].label).toBe("SETUP");
  });

  it("surfaces a server error", async () => {
    approveScript.mockRejectedValue(new Error("boom"));
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("calls onApproved after a successful submit", async () => {
    const onApproved = vi.fn();
    render(<ScriptEditor runId="r1" script={script} onApproved={onApproved} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(onApproved).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/ScriptEditor.test.tsx`
Expected: FAIL — cannot resolve `./ScriptEditor`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/ScriptEditor.tsx`:

```tsx
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { approveScript } from "@/lib/api";
import type { ScriptPayload, Section } from "@/lib/types";

interface Props {
  runId: string;
  script: ScriptPayload;
  onApproved: () => void;
}

/**
 * Edit the script and its drawings before any media is paid for.
 *
 * Editing narration deliberately does NOT recount drawings. The prompts are
 * already paired one-to-one with shots, and assembly divides each section's
 * measured audio by however many drawings it ends up with — so a shorter
 * narration simply means each drawing holds for less time. Add or remove a
 * drawing here to change the rhythm.
 */
export default function ScriptEditor({ runId, script, onApproved }: Props) {
  const [draft, setDraft] = useState<ScriptPayload>(() => ({
    ...script,
    sections: script.sections.map((section) => ({
      ...section,
      prompts: [...section.prompts],
    })),
  }));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateSection = (index: number, patch: Partial<Section>) =>
    setDraft((previous) => ({
      ...previous,
      sections: previous.sections.map((section, position) =>
        position === index ? { ...section, ...patch } : section,
      ),
    }));

  const updatePrompt = (index: number, promptIndex: number, value: string) =>
    updateSection(index, {
      prompts: draft.sections[index].prompts.map((prompt, position) =>
        position === promptIndex ? value : prompt,
      ),
    });

  const addPrompt = (index: number) =>
    updateSection(index, { prompts: [...draft.sections[index].prompts, ""] });

  const removePrompt = (index: number, promptIndex: number) =>
    updateSection(index, {
      prompts: draft.sections[index].prompts.filter(
        (_, position) => position !== promptIndex,
      ),
    });

  const removeSection = (index: number) =>
    setDraft((previous) => ({
      ...previous,
      sections: previous.sections.filter((_, position) => position !== index),
    }));

  const onApprove = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await approveScript(runId, draft);
      onApproved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Edit anything you want before images and narration are generated.
        Approving starts the paid work.
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Style sheet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          <Label htmlFor="style">Style sheet</Label>
          <Textarea
            id="style"
            value={draft.style}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, style: event.target.value }))
            }
          />
          <p className="text-xs text-muted-foreground">
            The recurring figures and colours for the whole video. Drawings do
            not carry over between sections, so this text is the only thing
            keeping them consistent across a cut.
          </p>
        </CardContent>
      </Card>

      {draft.sections.map((section, index) => (
        <Card key={index}>
          <CardHeader>
            <CardTitle className="text-base">Section {index + 1}</CardTitle>
            <CardAction>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove section ${index + 1}`}
                onClick={() => removeSection(index)}
              >
                Remove section
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor={`label-${index}`}>Section {index + 1} label</Label>
              <Input
                id={`label-${index}`}
                value={section.label}
                onChange={(event) =>
                  updateSection(index, { label: event.target.value })
                }
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor={`narration-${index}`}>
                Section {index + 1} narration
              </Label>
              <Textarea
                id={`narration-${index}`}
                rows={3}
                value={section.narration}
                onChange={(event) =>
                  updateSection(index, { narration: event.target.value })
                }
              />
              <p className="text-xs text-muted-foreground">
                {section.prompts.length} drawing(s) over this narration. Editing
                the words does not change that count — add or remove a drawing
                below to change the pace.
              </p>
            </div>

            <div className="space-y-3">
              {section.prompts.map((prompt, promptIndex) => (
                <div key={promptIndex} className="space-y-1 rounded border p-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`prompt-${index}-${promptIndex}`}>
                      Section {index + 1} drawing {promptIndex + 1}
                    </Label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove section ${index + 1} drawing ${promptIndex + 1}`}
                      onClick={() => removePrompt(index, promptIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                  <Input
                    id={`prompt-${index}-${promptIndex}`}
                    value={prompt}
                    onChange={(event) =>
                      updatePrompt(index, promptIndex, event.target.value)
                    }
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={`Add drawing to section ${index + 1}`}
                onClick={() => addPrompt(index)}
              >
                Add drawing
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button
        type="button"
        onClick={onApprove}
        disabled={submitting || draft.sections.length === 0}
      >
        {submitting ? "Approving..." : "Approve and generate media"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/ScriptEditor.test.tsx`
Expected: PASS, 9 tests.

- [ ] **Step 5: Delete the old editor**

```bash
git rm frontend/src/components/ItemEditor.tsx frontend/src/components/ItemEditor.test.tsx
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components
git commit -m "feat: review the script and its drawings before generating media"
```

---

### Task 15: New-run form and run page

**Files:**
- Modify: `frontend/src/pages/NewRunPage.tsx`, `frontend/src/pages/RunPage.tsx`, and their tests; `frontend/src/components/StageProgress.test.tsx`

- [ ] **Step 1: Update the tests first**

In `frontend/src/pages/NewRunPage.test.tsx`, replace assertions about "Number of items" with:

```tsx
  it("submits a target length in seconds", async () => {
    render(<NewRunPage />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Topic"), {
      target: { value: "how dogs evolved from wolves" },
    });
    fireEvent.change(screen.getByLabelText("Target length (seconds)"), {
      target: { value: "60" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(createRun.mock.calls[0][0]).toMatchObject({
      topic: "how dogs evolved from wolves",
      target_seconds: 60,
      review_script: false,
    });
  });
```

In `frontend/src/pages/RunPage.test.tsx`, replace the `ItemEditor` render assertion with one that renders `ScriptEditor` when `status === "awaiting_review"`, and update any fixture from `items: [...]` to `script: { topic, title, style, sections: [...] }` and `num_items` to `target_seconds`.

In `frontend/src/components/StageProgress.test.tsx`, update the expected stage labels to the seven in `STAGE_SEQUENCE`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run`
Expected: FAIL on the renamed fields and labels.

- [ ] **Step 3: Update `NewRunPage.tsx`**

Rename the state and the field:

```tsx
  const [targetSeconds, setTargetSeconds] = useState(85);
  const [reviewScript, setReviewScript] = useState(false);
```

```tsx
          <div className="space-y-2">
            <Label htmlFor="target-seconds">Target length (seconds)</Label>
            <Input
              id="target-seconds"
              type="number"
              min={15}
              max={180}
              value={targetSeconds}
              onChange={(event) => setTargetSeconds(Number(event.target.value))}
              className="w-32"
            />
            <p className="text-xs text-muted-foreground">
              Section and image counts follow from this — the script is written
              to fit, and a drawing lands about every 2.5 seconds.
            </p>
          </div>
```

Change the checkbox label to "Let me review the script before generating media", bind it to `reviewScript`, change the topic placeholder to `"how dogs evolved from wolves"`, and submit `target_seconds: targetSeconds, review_script: reviewScript`.

- [ ] **Step 4: Update `RunPage.tsx`**

Replace the `ItemEditor` import and usage with `ScriptEditor`, passing `script={run.script}` instead of `items={run.items}`. Update any display of `run.num_items` to `run.target_seconds` with a "s" suffix.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages frontend/src/components
git commit -m "feat: ask for a target length and review the script on the run page"
```

---

### Task 16: Archive browser pages

**Files:**
- Modify: `frontend/src/pages/ArchivesPage.tsx`, `frontend/src/pages/ArchiveDetailPage.tsx`, and their tests

- [ ] **Step 1: Update the tests first**

In `ArchivesPage.test.tsx`, change the fixture from `item_count` to `section_count` plus `legacy: false`, and add:

```tsx
  it("marks a legacy archive", async () => {
    listArchives.mockResolvedValue([
      { slug: "old_run", section_count: 0, image_count: 3, audio_count: 0, has_video: true, legacy: true, modified_at: "2026-01-01T00:00:00+00:00" },
    ]);
    render(<ArchivesPage />, { wrapper: MemoryRouter });
    expect(await screen.findByText(/legacy/i)).toBeInTheDocument();
  });
```

In `ArchiveDetailPage.test.tsx`, change the fixture to the section shape and add:

```tsx
  it("groups images under their section label", async () => {
    getArchive.mockResolvedValue({
      slug: "wolves",
      title: "Wolves Domesticated Themselves",
      style: "A grey-blue wolf.",
      video_url: "/media/generated_data/wolves/final_video_short.mp4",
      legacy: false,
      sections: [
        { label: "HOOK", narration: "One line.", start: 0, end: 5, prompts: ["p1"], image_urls: ["/i1.png"], composed_image_urls: [], audio_url: "/a.mp3" },
      ],
    });
    render(<ArchiveDetailPage />, { wrapper: MemoryRouter });
    expect(await screen.findByText("HOOK")).toBeInTheDocument();
    expect(screen.getByText("One line.")).toBeInTheDocument();
  });

  it("explains a legacy archive instead of rendering empty sections", async () => {
    getArchive.mockResolvedValue({
      slug: "old_run", title: "old run", style: "", video_url: "/v.mp4", legacy: true, sections: [],
    });
    render(<ArchiveDetailPage />, { wrapper: MemoryRouter });
    expect(await screen.findByText(/older format/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages`
Expected: FAIL on the renamed fields.

- [ ] **Step 3: Update the pages**

In `ArchivesPage.tsx`, render `section_count` where `item_count` was (column header "Sections"), and render a "Legacy" badge when `archive.legacy` is true.

In `ArchiveDetailPage.tsx`, show `title` as the heading and `style` beneath it, then branch on `legacy`. The copy matters — a test asserts on it:

```tsx
      {archive.legacy ? (
        <Alert>
          <AlertDescription>
            This run used an older format, so its script is not available. The
            video and its media files are still here.
          </AlertDescription>
        </Alert>
      ) : (
        archive.sections.map((section, index) => (
          <Card key={index}>
            <CardHeader>
              <CardTitle className="text-base">{section.label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{section.narration}</p>
              {section.audio_url && (
                <audio controls src={section.audio_url} className="w-full" />
              )}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {section.image_urls.map((url) => (
                  <img key={url} src={url} alt="" className="w-full rounded" />
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}
```

- [ ] **Step 4: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages
git commit -m "feat: browse archived scripts by section"
```

---

### Task 17: Documentation

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] **Step 1: Rewrite the pipeline description in `README.md`**

Replace the "Pipeline steps" list with:

```markdown
**Pipeline steps:**

1. Write a script for the topic: a title plus free-form sections, each a short
   paragraph of narration. The model writes to a word budget derived from
   `TARGET_VIDEO_SECONDS` that already accounts for the pause the voice leaves
   after every sentence — the naive words-per-second figure overshoots by
   roughly 40%.
2. Design the drawings in a second call that sees the whole script: one global
   style sheet plus one prompt per shot, where a section earns one shot per
   `SECONDS_PER_IMAGE` of estimated narration.
3. Narrate each section and draw every shot, capped at
   `MAX_CONCURRENT_REQUESTS` concurrent API calls. A section's shots are drawn
   in sequence, each continuing the one before it; sections are independent and
   run in parallel, so the look resets at every section boundary and the style
   sheet is what carries a character across the cut.
4. Verify every expected asset exists before continuing.
5. Compose each image onto a blurred 1080x1920 backdrop.
6. Assemble the frames and narration into a vertical video, splitting each
   section's measured audio evenly across its shots.
7. Archive the run into `generated_data/<topic-slug>/`, rewriting `script.json`
   with the measured section timings.
```

- [ ] **Step 2: Update the configuration table**

Replace the `IMAGE_PROMPTS_PER_ITEM` row and add the new ones:

```markdown
| `TARGET_VIDEO_SECONDS` | `85` | Target spoken length. Section and image counts follow from it. |
| `SECONDS_PER_IMAGE` | `2.5` | How long one drawing holds. Not env-overridable; change it in `config.py`. |
| `TEXT_MODEL` | `gpt-4.1-mini` | Writes the script and the drawing prompts. Must support JSON schema structured outputs. |
```

Update the "How to Run the App" section: `--items N` becomes `--seconds N`.

- [ ] **Step 3: Update `.env.example`**

Replace the `IMAGE_PROMPTS_PER_ITEM` line with `TARGET_VIDEO_SECONDS=85`.

- [ ] **Step 4: Verify the documented commands still work**

```bash
venv/bin/python main.py --help
```
Expected: the help text shows `--seconds`, not `--items`.

- [ ] **Step 5: Run everything one last time**

```bash
venv/bin/pytest && cd frontend && npx vitest run
```
Expected: PASS on both.

- [ ] **Step 6: Commit**

```bash
git add README.md .env.example
git commit -m "docs: describe the sectioned script pipeline"
```

---

## Verification

After Task 17, confirm the whole migration landed:

```bash
venv/bin/pytest
cd frontend && npx vitest run && npx tsc --noEmit
grep -rn "num_items\|IMAGE_PROMPTS_PER_ITEM\|ItemPayload\|titled_image" \
  --exclude-dir=venv --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=docs .
```

The grep must return nothing. Then run one real generation end to end and watch for the two things unit tests cannot catch:

```bash
venv/bin/python main.py --topic "how dogs evolved from wolves" --seconds 85
```

- **Length.** The finished video should land within a few seconds of 85. Materially longer means `NARRATION_WORDS_PER_SECOND` or `NARRATION_SENTENCE_PAUSE_SECONDS` is stale for the current `TTS_VOICE`; re-solve both from the rendered audio rather than adjusting the word budget by hand.
- **Section boundaries.** Listen across each cut. A gap means silence is still being applied per section rather than only at the two ends.
