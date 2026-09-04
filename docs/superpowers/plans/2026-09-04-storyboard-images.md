# Storyboard Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace each item's three unrelated images with an ordered sequence of stick-figure frames that continue one another and land on the narration they illustrate.

**Architecture:** An `Item` becomes a per-item style sheet plus an ordered list of `Beat`s, each pairing one sentence of narration with the drawing that illustrates it. Image generation runs in two waves — anchor frames via `images.generate`, then follow-up frames via `images.edit` referencing their item's anchor — so frames stay visually consistent without losing parallelism. Video timing splits each item's narration proportionally to beat word count instead of evenly.

**Tech Stack:** Python 3.12, OpenAI SDK 3.2.0 (`gpt-image-1`, `gpt-4.1-mini`), pytest, moviepy, Pillow, FastAPI + Pydantic v2, React 19 + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-04-storyboard-images-design.md`

## Global Constraints

- This is a **replacement, not a second mode**. The "straightforward / hilariously funny / different perspective" prompt strategy is deleted. There is one prompt path.
- **Every existing `generated_data/` archive must keep loading and rendering.** Items stored in the old `{title, description, image_prompts}` shape parse through a legacy path throughout.
- **`description` is derived** from the beat narrations whenever any narration is present; it is only read from stored JSON when every narration is empty (the legacy shape).
- **Beat count reuses `IMAGE_PROMPTS_PER_ITEM`**, read at call time so per-run overrides apply. No new count knob.
- Every image prompt sent to the API is `config.STORYBOARD_STYLE` + the item's `style` + the beat's `prompt`, in that order, joined by `" "`.
- The titled-image stage (`scripts/non_ai/create_titled_images_short/`) is **not modified** by this plan.
- Run Python tests with `pytest` from the repo root; frontend tests with `npm test` from `frontend/`.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `models.py` | `Beat`, `Item`, dual-shape `parse_items`, derived description | 2 |
| `config.py` | `STORYBOARD_STYLE` constant | 3 |
| `api/config_view.py` | `STORYBOARD_STYLE` overridable, reworded `IMAGE_PROMPTS_PER_ITEM` | 3 |
| `scripts/ai/generate_list/generate_list.py` | Storyboard JSON schema and authoring prompt | 3 |
| `scripts/ai/generate_images/utils.py` | `generate_image_from_reference` (`images.edit`) | 4 |
| `scripts/ai/generate_images/generate_images.py` | `anchor_jobs` / `followup_jobs` | 5 |
| `pipeline.py` | Two-wave media stage | 6 |
| `scripts/non_ai/generate_video_short/utils.py` | Weighted `segment_bounds`, `build_item_clip(item)` | 7 |
| `scripts/non_ai/generate_video_short/generate_video_short.py` | Passes items through | 7 |
| `api/schemas.py` | `BeatPayload`, extended `ItemPayload` / `ArchiveItemPayload` | 8 |
| `api/archives.py` | Emits `style` and `beats` | 8 |
| `frontend/src/lib/types.ts` | Wire mirror | 9 |
| `frontend/src/components/ItemEditor.tsx` | Beat editing | 9 |
| `frontend/src/pages/ArchiveDetailPage.tsx` | Beat display | 10 |
| `README.md` | Pipeline description | 10 |

---

### Task 1: Confirm `images.edit` honours a reference image

This is a **throwaway spike**, not production code. It answers the one question the rest of the plan is built on: does `client.images.edit(model="gpt-image-1", image=[anchor], prompt=...)` accept a reference image and carry its character and style into the new frame?

**Files:**
- Create (throwaway): `/tmp/claude-501/-Users-filippopovski-Documents-personal-auto-youtube-generator/19986f71-1664-4af7-8274-e7b45ea12f5e/scratchpad/probe_edit.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a yes/no answer that gates Tasks 4 and 5. Nothing importable.

- [ ] **Step 1: Write the probe script**

```python
"""Throwaway: does images.edit carry a reference frame's character forward?"""

import base64
from pathlib import Path

from utils.open_ai_client import get_open_ai_client

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

STYLE = (
    "Black ink outline drawing on a plain white background. Stick-figure "
    "people with simple round heads and minimal interior detail. No shading, "
    "no colour, no text or lettering."
)
SHEET = (
    "A reclusive scientist: round head, wild scribble hair, round glasses, "
    "long coat."
)

client = get_open_ai_client()

anchor_bytes = base64.b64decode(
    client.images.generate(
        model="gpt-image-1",
        prompt=f"{STYLE} {SHEET} The scientist stands alone in an empty room.",
        size="1024x1024",
        n=1,
        quality="medium",
    ).data[0].b64_json
)
(OUT / "anchor.png").write_bytes(anchor_bytes)
print("anchor written")

with open(OUT / "anchor.png", "rb") as reference:
    follow_up = client.images.edit(
        model="gpt-image-1",
        image=[reference],
        prompt=(
            f"{STYLE} {SHEET} Keep the same character exactly as in the "
            f"reference image. Same scientist, now beside a tall box; two "
            f"circles hang from a thread inside."
        ),
        size="1024x1024",
        n=1,
        quality="medium",
    )
(OUT / "follow_up.png").write_bytes(base64.b64decode(follow_up.data[0].b64_json))
print("follow-up written")
```

- [ ] **Step 2: Run it**

```bash
./venv/bin/python /tmp/claude-501/-Users-filippopovski-Documents-personal-auto-youtube-generator/19986f71-1664-4af7-8274-e7b45ea12f5e/scratchpad/probe_edit.py
```

Expected: both files written, no exception. The call signature is what matters most — that `image=[file_object]` is accepted alongside `model`, `size`, `n` and `quality`, and that the response has the same `data[0].b64_json` shape as `images.generate`.

- [ ] **Step 3: Look at both PNGs and decide**

Open `probe_out/anchor.png` and `probe_out/follow_up.png`. The question is whether the second drawing is recognisably the same figure in the same style.

- **Yes** — proceed to Task 2 as written.
- **No, or `images.edit` rejects the call** — STOP and report to the user. The fallback documented in the spec is to drop wave B and generate every frame independently with the style sheet prepended: Tasks 4, 5 and 6 collapse into "keep `image_jobs` as one flat list, prefix every prompt with `STORYBOARD_STYLE` + item style". Every other task stands unchanged.

- [ ] **Step 4: Delete the probe**

```bash
rm -rf probe_out /tmp/claude-501/-Users-filippopovski-Documents-personal-auto-youtube-generator/19986f71-1664-4af7-8274-e7b45ea12f5e/scratchpad/probe_edit.py
```

Nothing is committed by this task.

---

### Task 2: `Beat` and the storyboard `Item`

**Files:**
- Modify: `models.py` (whole file)
- Test: `tests/test_models.py`
- Modify (mechanical migration): `tests/test_video.py:76`, `tests/test_generate_images.py:38-39`, `tests/test_titled_images.py:134,150`, `tests/test_pipeline.py:12,70,78,91`, `tests/test_generate_audio.py:33-34`, `tests/test_archive.py:24`, `tests/api/test_runs.py:10,65`, `tests/api/test_routes.py:12`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Beat(narration: str, prompt: str)` — frozen dataclass, `to_dict() -> dict`.
  - `Item(title: str, description: str, beats: tuple[Beat, ...], style: str = "")` — frozen dataclass.
  - `Item.image_prompts -> tuple[str, ...]` — property deriving prompts from beats.
  - `Item.narration -> str` — unchanged, `f"{title}. {description}"`.
  - `Item.from_prompts(title, description, prompts, style="") -> Item` — classmethod building beats with empty narration.
  - `parse_items(raw, *, expected_prompts=config.IMAGE_PROMPTS_PER_ITEM) -> list[Item]` — signature unchanged.
  - `items_to_json`, `save_items`, `load_items` — signatures unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py`, and add `Beat` to the existing `from models import (...)` block:

```python
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
    assert item.image_prompts == ("a dodo", "a dodo on a skateboard", "a dodo, watercolour")
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
```

Then change the beat-count message assertion in the existing test:

```python
def test_rejects_wrong_prompt_count():
    broken = dict(VALID_ITEM, image_prompts=["only one"])
    with pytest.raises(InvalidItemsError, match="item 1.*3 story beats.*got 1"):
        parse_items([broken], expected_prompts=3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Beat' from 'models'`.

- [ ] **Step 3: Rewrite the model**

Replace the `Item` dataclass and the parsing helpers in `models.py`:

```python
@dataclass(frozen=True)
class Beat:
    """One narrated moment and the drawing that illustrates it."""

    narration: str
    prompt: str

    def to_dict(self) -> dict[str, Any]:
        return {"narration": self.narration, "prompt": self.prompt}


@dataclass(frozen=True)
class Item:
    title: str
    description: str
    beats: tuple[Beat, ...]
    style: str = ""

    @classmethod
    def from_prompts(
        cls,
        title: str,
        description: str,
        prompts: Sequence[str],
        style: str = "",
    ) -> "Item":
        """Build an item from bare prompt strings — the pre-storyboard shape."""
        return cls(
            title=title,
            description=description,
            beats=tuple(Beat("", prompt) for prompt in prompts),
            style=style,
        )

    @property
    def image_prompts(self) -> tuple[str, ...]:
        """The drawing prompts alone. Keeps pre-storyboard callers working."""
        return tuple(beat.prompt for beat in self.beats)

    @property
    def narration(self) -> str:
        """The text handed to the text-to-speech model."""
        return f"{self.title}. {self.description}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "style": self.style,
            "description": self.description,
            "beats": [beat.to_dict() for beat in self.beats],
        }
```

Add the beat parser above `parse_items`:

```python
def _parse_beats(payload: dict, position: int) -> tuple[Beat, ...]:
    """Read an item's beats from either the storyboard or the legacy shape.

    An empty `beats` list is treated as absent, not as an error: the review
    editor posts `beats: []` for items it loaded in the legacy shape.
    """
    raw = payload.get("beats")
    if raw:
        if not isinstance(raw, list):
            raise InvalidItemsError(
                f"item {position} has a malformed 'beats' list "
                f"(got {type(raw).__name__})"
            )
        beats: list[Beat] = []
        for beat_position, entry in enumerate(raw, start=1):
            if not isinstance(entry, dict):
                raise InvalidItemsError(
                    f"item {position} beat {beat_position} is not an object "
                    f"(got {type(entry).__name__})"
                )
            narration = entry.get("narration")
            if not isinstance(narration, str):
                raise InvalidItemsError(
                    f"item {position} beat {beat_position} is missing a "
                    f"'narration' string (got {narration!r})"
                )
            beats.append(
                Beat(narration.strip(), _required_text(entry, "prompt", position))
            )
        return tuple(beats)

    prompts = payload.get("image_prompts")
    if (
        not isinstance(prompts, list)
        or not prompts
        or not all(isinstance(p, str) and p.strip() for p in prompts)
    ):
        raise InvalidItemsError(
            f"item {position} is missing a usable 'beats' or 'image_prompts' list"
        )
    return tuple(Beat("", prompt.strip()) for prompt in prompts)
```

Replace the per-item body of the `parse_items` loop (everything after the `isinstance(payload, dict)` guard) with:

```python
        title = _required_text(payload, "title", position)
        beats = _parse_beats(payload, position)

        if expected_prompts is not None and len(beats) != expected_prompts:
            raise InvalidItemsError(
                f"item {position} needs exactly {expected_prompts} story beats, "
                f"got {len(beats)}"
            )

        # Derived whenever the beats carry narration; only the legacy shape,
        # whose narrations are all empty, falls back to the stored field.
        narrated = " ".join(beat.narration for beat in beats if beat.narration)
        description = narrated.strip() or _required_text(
            payload, "description", position
        )

        items.append(
            Item(
                title=title,
                description=description,
                beats=beats,
                style=str(payload.get("style") or "").strip(),
            )
        )
```

- [ ] **Step 4: Run the model tests**

Run: `pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Migrate the positional `Item(...)` call sites**

Eighteen call sites construct `Item(title, description, tuple_of_prompt_strings)`. The third positional argument is now `beats`, so each becomes `Item.from_prompts(...)`.

```bash
sed -i '' 's/\bItem(\("[^"]*", "[^"]*", (\)/Item.from_prompts(\1/g' \
  tests/test_video.py tests/test_generate_images.py tests/test_titled_images.py \
  tests/test_pipeline.py tests/test_generate_audio.py tests/test_archive.py \
  tests/api/test_runs.py tests/api/test_routes.py
grep -rn "Item(" tests | grep -v "from_prompts\|ItemPayload\|ArchiveItem\|InvalidItems"
```

The `grep` must print nothing. If it prints a line, fix that call by hand — `models.py:111` inside `parse_items` is the only legitimate bare `Item(` in the codebase and it is not under `tests/`.

- [ ] **Step 6: Run the whole Python suite**

Run: `pytest -q`
Expected: PASS. Everything except `models.py` still reads `item.image_prompts`, which is now a property over the beats.

- [ ] **Step 7: Commit**

```bash
git add models.py tests/
git commit -m "feat: model items as a style sheet plus ordered story beats"
```

---

### Task 3: Storyboard authoring — config and list generation

**Files:**
- Modify: `config.py` (add `STORYBOARD_STYLE` in the "OpenAI models" section)
- Modify: `api/config_view.py:31-52` (the `OVERRIDABLE` tuple)
- Modify: `scripts/ai/generate_list/generate_list.py` (whole file)
- Test: `tests/test_generate_list.py`, `tests/api/test_config_view.py`

**Interfaces:**
- Consumes: `Beat`, `Item`, `parse_items` from Task 2.
- Produces:
  - `config.STORYBOARD_STYLE: str`
  - `LIST_JSON_SCHEMA` — the storyboard schema, still exported for the schema test.
  - `generate_list(topic, num_items=5, *, client=None) -> list[Item]` — signature unchanged.

- [ ] **Step 1: Write the failing tests**

Replace `build_payload` in `tests/test_generate_list.py` and add the new cases:

```python
def build_payload(count=3, beats=3):
    return {
        "items": [
            {
                "title": f"Item {i}",
                "style": f"A recurring figure for item {i}.",
                "beats": [
                    {"narration": f"Sentence {i}.{j}.", "prompt": f"prompt {i}.{j}"}
                    for j in range(beats)
                ],
            }
            for i in range(1, count + 1)
        ]
    }


def test_returns_typed_items():
    client = FakeClient(json.dumps(build_payload(count=3)))
    items = generate_list("extinct animals", 3, client=client)
    assert len(items) == 3
    assert items[0].title == "Item 1"
    assert len(items[0].beats) == 3
    assert items[0].style == "A recurring figure for item 1."


def test_schema_requires_style_and_beats():
    item_schema = LIST_JSON_SCHEMA["properties"]["items"]["items"]
    assert set(item_schema["required"]) == {"title", "style", "beats"}
    beat_schema = item_schema["properties"]["beats"]["items"]
    assert set(beat_schema["required"]) == {"narration", "prompt"}


def test_rejects_the_wrong_number_of_beats(monkeypatch):
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 3)
    client = FakeClient(json.dumps(build_payload(count=1, beats=2)))
    with pytest.raises(InvalidItemsError, match="3 story beats"):
        generate_list("extinct animals", 1, client=client)


def test_prompt_asks_for_a_continuing_sequence():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "continuation" in user_message
    assert "one sentence" in user_message


def test_prompt_states_the_beat_count(monkeypatch):
    monkeypatch.setattr("config.IMAGE_PROMPTS_PER_ITEM", 5)
    client = FakeClient(json.dumps(build_payload(beats=5)))
    generate_list("extinct animals", 3, client=client)
    assert "exactly 5" in client.calls[0]["messages"][1]["content"]
```

Add to `tests/api/test_config_view.py`:

```python
def test_storyboard_style_is_overridable():
    assert any(field.name == "STORYBOARD_STYLE" for field in OVERRIDABLE)
    assert validate_overrides({"STORYBOARD_STYLE": "  crayon doodles  "}) == {
        "STORYBOARD_STYLE": "crayon doodles"
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_generate_list.py tests/api/test_config_view.py -v`
Expected: FAIL — `KeyError: 'style'` on the schema test and `ConfigOverrideError: STORYBOARD_STYLE is not overridable`.

- [ ] **Step 3: Add the config constant**

In `config.py`, directly below the `IMAGE_QUALITY` line:

```python
# The fixed look every generated frame shares. Prepended to every image
# prompt, in front of the item's own style sheet.
STORYBOARD_STYLE = _env_str(
    "STORYBOARD_STYLE",
    "Black ink outline drawing on a plain white background. Stick-figure "
    "people with simple round heads and minimal interior detail. Clean even "
    "line weight, no shading, no colour, no text or lettering.",
)
```

- [ ] **Step 4: Expose it and reword the beat-count field**

In `api/config_view.py`, inside the `OVERRIDABLE` tuple, replace the `IMAGE_PROMPTS_PER_ITEM` entry with these two:

```python
    OverridableField(
        "STORYBOARD_STYLE", "str", None, "The drawing style every frame shares."
    ),
    OverridableField(
        "IMAGE_PROMPTS_PER_ITEM",
        "int",
        None,
        "Story beats per item. Sets both the frame count and, at one sentence "
        "per beat, the narration length.",
    ),
```

- [ ] **Step 5: Rewrite the list schema and prompt**

In `scripts/ai/generate_list/generate_list.py`, replace `SYSTEM_MESSAGE`, `LIST_JSON_SCHEMA` and `_build_user_message`. Everything below them — `_request_items` and `generate_list` — is unchanged.

```python
SYSTEM_MESSAGE = (
    "You are a storyboard writer. For each subject you write a short narrated "
    "story and the sequence of simple line drawings that illustrates it, where "
    "each drawing continues the one before it. Always ensure all content is "
    "family-friendly and appropriate for all audiences."
)

LIST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "The generated video items, in presentation order.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Very short subject name, no extra words.",
                    },
                    "style": {
                        "type": "string",
                        "description": (
                            "The recurring figure(s) and setting for this "
                            "item's drawings, described concretely enough to "
                            "be redrawn identically every time."
                        ),
                    },
                    "beats": {
                        "type": "array",
                        "description": "The story beats, in narration order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "narration": {
                                    "type": "string",
                                    "description": "One spoken sentence.",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": (
                                        "The drawing for this sentence, as a "
                                        "continuation of the previous one."
                                    ),
                                },
                            },
                            "required": ["narration", "prompt"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "style", "beats"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _build_user_message(topic: str, num_items: int) -> str:
    beat_count = config.IMAGE_PROMPTS_PER_ITEM
    return (
        f"Give me a list of {num_items} items for a YouTube video on the topic: "
        f"'{topic}'.\n"
        f"Each item is a tiny narrated story told through a sequence of simple "
        f"line drawings. Every item must have:\n"
        f"1. A very short, concise title (just the main subject/name, no "
        f"additional descriptive text)\n"
        f"2. A 'style' line naming the recurring figure(s) and setting for this "
        f"item — their build, hair, clothing, props and surroundings — described "
        f"concretely enough that an illustrator could redraw them identically "
        f"in every frame. Describe only what is drawn; do not name a medium or "
        f"an art style.\n"
        f"3. Exactly {beat_count} beats, in order. Each beat has:\n"
        f"   - 'narration': one sentence of the spoken script. Read in order, "
        f"the {beat_count} sentences must flow as continuous, informative, "
        f"intriguing prose about the item.\n"
        f"   - 'prompt': what the drawing shows at that moment, written as a "
        f"continuation of the previous drawing. Keep the same figure and the "
        f"same setting, and change or add exactly one thing per beat. Refer "
        f"back explicitly, for example 'the same scientist, now beside the "
        f"apparatus'.\n"
        f"The first beat establishes the subject alone. Each later beat adds "
        f"the element its sentence introduces, so the drawings track the "
        f"narration as it plays.\n"
        f"\n"
        f"DRAWING CONSTRAINTS:\n"
        f"- The drawings are plain black outline sketches with stick-figure "
        f"people. Describe simple shapes, poses and objects only.\n"
        f"- Never ask for text, letters, numbers or labels in a drawing.\n"
        f"- Never ask for colour, shading, texture or photographic detail.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES FOR IMAGE PROMPTS:\n"
        f"- All prompts must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Avoid any content that could be considered violent, graphic, or "
        f"inappropriate\n"
        f"- Do not include prompts that could generate images of weapons, gore, "
        f"or harmful content\n"
        f"- Avoid prompts that could create images with nudity, sexual content, "
        f"or adult themes\n"
        f"- Ensure all prompts are educational, informative, or entertaining in "
        f"a wholesome way\n"
        f"- If the topic involves potentially sensitive subjects, focus on "
        f"positive, educational, or neutral representations\n"
        f"\n"
        f"COPYRIGHT AND INTELLECTUAL PROPERTY GUIDELINES:\n"
        f"- NEVER include copyrighted characters, brands, or intellectual "
        f"property in prompts\n"
        f"- Avoid specific character names like 'Yoda', 'Mickey Mouse', "
        f"'Superman', 'Mario', etc.\n"
        f"- Instead of copyrighted characters, use generic descriptions (e.g., "
        f"'wise green alien mentor' instead of 'Yoda')\n"
        f"- Avoid famous logos, brand names, or trademarked symbols\n"
        f"- Create original, generic descriptions that capture the essence "
        f"without infringing on copyrights\n"
        f"- Focus on visual concepts, emotions, and themes rather than specific "
        f"copyrighted entities\n"
        f"- Use descriptive terms like 'heroic figure', 'wise mentor', 'cute "
        f"animal companion' instead of specific character names"
    )
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_generate_list.py tests/api/test_config_view.py -v`
Expected: PASS.

- [ ] **Step 7: Run the whole Python suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add config.py api/config_view.py scripts/ai/generate_list/generate_list.py tests/
git commit -m "feat: ask the model for narrated story beats and a per-item style sheet"
```

---

### Task 4: Generate a frame from a reference frame

**Files:**
- Modify: `scripts/ai/generate_images/utils.py`
- Test: `tests/test_generate_images.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `styled_prompt(item_style: str, prompt: str) -> str` — joins `config.STORYBOARD_STYLE`, the item style and the beat prompt with single spaces, skipping blanks.
  - `generate_image_from_reference(prompt: str, reference: Path, destination: Path, *, client=None) -> Path` — decorated with `@with_retry`, same write-through-temporary behaviour as `generate_image`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generate_images.py`. Extend `FakeImages` with an `edit` method and import the new names:

```python
from scripts.ai.generate_images.utils import (
    generate_image,
    generate_image_from_reference,
    styled_prompt,
)
```

```python
def test_styled_prompt_orders_global_style_then_item_then_beat(monkeypatch):
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    assert styled_prompt("ITEM.", "BEAT.") == "GLOBAL. ITEM. BEAT."


def test_styled_prompt_skips_a_blank_item_style(monkeypatch):
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    assert styled_prompt("", "BEAT.") == "GLOBAL. BEAT."


def test_generate_from_reference_sends_the_reference_file(tmp_path):
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    destination = tmp_path / "follow_up.png"

    result = generate_image_from_reference("beat two", reference, destination, client=client)

    assert result == destination
    assert destination.read_bytes() == PNG_BYTES
    assert images.calls == []  # it used edit, not generate
    assert len(images.edits) == 1
    assert images.edits[0]["prompt"] == "beat two"
    assert images.edits[0]["reference_bytes"] == PNG_BYTES


def test_generate_from_reference_passes_configured_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr("config.IMAGE_MODEL", "test-image-model")
    monkeypatch.setattr("config.IMAGE_QUALITY", "high")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    generate_image_from_reference("beat two", reference, tmp_path / "out.png", client=client)
    assert images.edits[0]["model"] == "test-image-model"
    assert images.edits[0]["quality"] == "high"
    assert images.edits[0]["n"] == 1


def test_generate_from_reference_fails_loudly_without_an_anchor(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    with pytest.raises(FileNotFoundError, match="anchor frame"):
        generate_image_from_reference(
            "beat two", tmp_path / "missing.png", tmp_path / "out.png", client=client
        )


def test_generate_from_reference_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(b64=None)
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    destination = tmp_path / "out.png"
    with pytest.raises(ValueError, match="No image data"):
        generate_image_from_reference("beat two", reference, destination, client=client)
    assert not destination.exists()
```

Replace the `FakeImages` class so it records edits and reads the file handle before it closes:

```python
class FakeImages:
    def __init__(self, b64=None, error=None):
        self.b64 = b64
        self.error = error
        self.calls = []
        self.edits = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])

    def edit(self, **kwargs):
        # The handle is closed once the caller's `with` block exits, so read
        # it now and record the bytes rather than the file object.
        recorded = dict(kwargs)
        recorded["reference_bytes"] = kwargs["image"][0].read()
        self.edits.append(recorded)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_generate_images.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_image_from_reference'`.

- [ ] **Step 3: Implement both helpers**

Add to `scripts/ai/generate_images/utils.py`. Factor the shared tail out of `generate_image` first:

```python
def styled_prompt(item_style: str, prompt: str) -> str:
    """The global look, then the item's style sheet, then the beat itself."""
    parts = [config.STORYBOARD_STYLE, item_style.strip(), prompt.strip()]
    return " ".join(part for part in parts if part)


def _write_image(response, destination: Path, prompt: str) -> Path:
    """Decode one image response and write it atomically."""
    if not response.data or not response.data[0] or not response.data[0].b64_json:
        raise ValueError(f"No image data returned from API for prompt: {prompt!r}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(base64.b64decode(response.data[0].b64_json))
    os.replace(temporary, destination)
    return destination


@with_retry
def generate_image_from_reference(
    prompt: str, reference: Path, destination: Path, *, client=None
) -> Path:
    """Draw `prompt` as a continuation of the already-generated `reference`.

    The reference is what keeps a character recognisable across an item's
    frames; a text style sheet alone lets the figure drift.
    """
    client = client or get_open_ai_client()
    reference = Path(reference)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not reference.is_file() or reference.stat().st_size == 0:
        raise FileNotFoundError(
            f"anchor frame is missing or empty, cannot continue from it: {reference}"
        )

    with reference.open("rb") as handle:
        response = client.images.edit(
            model=config.IMAGE_MODEL,
            image=[handle],
            prompt=prompt,
            size=config.IMAGE_SIZE,
            n=1,
            quality=config.IMAGE_QUALITY,
        )

    return _write_image(response, destination, prompt)
```

Then rewrite the tail of `generate_image` to call the shared helper:

```python
    response = client.images.generate(
        model=config.IMAGE_MODEL,
        prompt=prompt,
        size=config.IMAGE_SIZE,
        n=1,
        quality=config.IMAGE_QUALITY,
    )

    return _write_image(response, destination, prompt)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_generate_images.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/generate_images/utils.py tests/test_generate_images.py
git commit -m "feat: generate a frame as a continuation of a reference frame"
```

---

### Task 5: Two-wave job builders

**Files:**
- Modify: `scripts/ai/generate_images/generate_images.py` (whole file)
- Test: `tests/test_generate_images.py`

**Interfaces:**
- Consumes: `styled_prompt`, `generate_image_from_reference` (Task 4); `Item.beats`, `Item.style` (Task 2).
- Produces:
  - `anchor_jobs(items, *, client=None) -> list[Job]` — one job per item, beat 1, via `generate_image`. Label: `f"image item {n} beat 1"`.
  - `followup_jobs(items, *, client=None) -> list[Job]` — one job per `(item, beat 2..N)`, via `generate_image_from_reference` against `image_path(n, 1)`. Label: `f"image item {n} beat {b}"`.
  - `generate_images(items, *, client=None) -> list[TaskResult]` — runs both waves, returns anchors then follow-ups.
- **Removed:** `image_jobs`. Task 6 replaces its only production caller.

- [ ] **Step 1: Write the failing tests**

Replace the `image_jobs` tests in `tests/test_generate_images.py` with these, and update the import to `from scripts.ai.generate_images.generate_images import anchor_jobs, followup_jobs, generate_images`:

```python
def two_items():
    return [
        Item("A", "First.", (Beat("n1", "a1"), Beat("n2", "a2"), Beat("n3", "a3")), "STYLE A."),
        Item("B", "Second.", (Beat("n4", "b1"), Beat("n5", "b2"), Beat("n6", "b3")), "STYLE B."),
    ]


def test_anchor_jobs_is_one_per_item():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    jobs = anchor_jobs(two_items(), client=client)
    assert [label for label, _ in jobs] == ["image item 1 beat 1", "image item 2 beat 1"]


def test_followup_jobs_covers_every_later_beat():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    labels = [label for label, _ in followup_jobs(two_items(), client=client)]
    assert labels == [
        "image item 1 beat 2",
        "image item 1 beat 3",
        "image item 2 beat 2",
        "image item 2 beat 3",
    ]


def test_followup_jobs_is_empty_for_single_beat_items():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    items = [Item("A", "First.", (Beat("n", "a1"),), "STYLE A.")]
    assert followup_jobs(items, client=client) == []


def test_jobs_are_not_executed_when_built():
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    anchor_jobs(two_items(), client=client)
    followup_jobs(two_items(), client=client)
    assert images.calls == []
    assert images.edits == []


def test_anchor_prompts_carry_the_global_and_item_style(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    assert images.calls[0]["prompt"] == "GLOBAL. STYLE A. a1"
    assert images.calls[1]["prompt"] == "GLOBAL. STYLE B. b1"


def test_followup_prompts_carry_the_global_and_item_style(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    for _, run in followup_jobs(two_items(), client=client):
        run()
    assert images.edits[0]["prompt"] == "GLOBAL. STYLE A. a2"
    assert images.edits[-1]["prompt"] == "GLOBAL. STYLE B. b3"


def test_followups_read_their_own_items_anchor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    label, run = followup_jobs(two_items(), client=client)[2]  # item 2 beat 2
    run()
    assert label == "image item 2 beat 2"
    assert Path("outputs/image_output/item_02_prompt_02.png").exists()


def test_generate_images_writes_every_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    results = generate_images(two_items(), client=client)
    assert all(r.ok for r in results)
    assert len(results) == 6
    assert Path("outputs/image_output/item_01_prompt_01.png").exists()
    assert Path("outputs/image_output/item_02_prompt_03.png").exists()


def test_a_failed_anchor_fails_its_followups_rather_than_vanishing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    original = images.generate

    def fail_item_one(**kwargs):
        if kwargs["prompt"].endswith("a1"):
            raise RuntimeError("content filtered")
        return original(**kwargs)

    images.generate = fail_item_one
    results = generate_images(two_items(), client=client)

    failed = {r.label: r for r in results if not r.ok}
    assert set(failed) == {"image item 1 beat 1", "image item 1 beat 2", "image item 1 beat 3"}
    assert isinstance(failed["image item 1 beat 2"].error, FileNotFoundError)
```

Add `Beat` to the `from models import ...` line, and delete the now-obsolete tests `test_image_jobs_fans_out_one_job_per_prompt`, `test_image_jobs_labels_identify_item_and_prompt`, `test_generate_images_reports_failures_without_stopping` and `test_jobs_run_correctly_through_the_shared_runner`.

- [ ] **Step 2: Leave the output filenames alone**

Job *labels* become `image item N beat B`, but the files on disk stay
`item_NN_prompt_NN.png`. `utils/paths.py` is not modified by this task.

Renaming them would churn several test files and make new archives
inconsistent with the existing ones in `generated_data/`, for no functional
gain — `api/archives.py` joins files to items by the `item_NN_` prefix, which
is unaffected either way.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_generate_images.py -v`
Expected: FAIL with `ImportError: cannot import name 'anchor_jobs'`.

- [ ] **Step 4: Rewrite the job builders**

Replace the body of `scripts/ai/generate_images/generate_images.py`:

```python
"""Fan an item's story beats out into anchor and follow-up image jobs.

Frames 2..N of an item are drawn as continuations of frame 1, so they cannot
run until it exists. Splitting them into two waves keeps every job independent
within its wave — the alternative, one sequential job per item, would cut
parallelism to the item count and coarsen the progress display.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path

from .utils import generate_image, generate_image_from_reference, styled_prompt


def anchor_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """One job per item: its first frame, drawn from the prompt alone."""
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        if not item.beats:
            continue
        prompt = styled_prompt(item.style, item.beats[0].prompt)
        destination = image_path(item_number, 1)
        jobs.append(
            (
                f"image item {item_number} beat 1",
                lambda p=prompt, d=destination: generate_image(p, d, client=client),
            )
        )
    return jobs


def followup_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """One job per later beat, each continuing its own item's anchor frame.

    Build these only after the anchor wave has run. A job whose anchor is
    missing raises `FileNotFoundError`, so a failed anchor is reported against
    every frame it blocked instead of silently producing nothing.
    """
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        reference = image_path(item_number, 1)
        for beat_number, beat in enumerate(item.beats[1:], start=2):
            prompt = styled_prompt(item.style, beat.prompt)
            destination = image_path(item_number, beat_number)
            jobs.append(
                (
                    f"image item {item_number} beat {beat_number}",
                    lambda p=prompt, r=reference, d=destination: (
                        generate_image_from_reference(p, r, d, client=client)
                    ),
                )
            )
    return jobs


def generate_images(items: Sequence[Item], *, client=None) -> list[TaskResult]:
    """Run both waves in order. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        anchors = run_all(executor, anchor_jobs(items, client=client))
        followups = run_all(executor, followup_jobs(items, client=client))
    return anchors + followups
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_generate_images.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

`pipeline.py` still imports `image_jobs` and will fail until Task 6, so commit the two together if `pytest -q` is red here. Otherwise:

```bash
git add scripts/ai/generate_images/generate_images.py tests/test_generate_images.py
git commit -m "feat: split image generation into anchor and follow-up waves"
```

---

### Task 6: Run the media stage in two waves

**Files:**
- Modify: `pipeline.py:105-135` (`generate_media_stage`) and its imports; `missing_media`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `anchor_jobs`, `followup_jobs` (Task 5).
- Produces: `generate_media_stage(items, *, client=None, log=print, on_asset=None) -> None` — signature unchanged. `media_job_total(items)` unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def test_media_stage_runs_anchors_before_followups(tmp_path, monkeypatch):
    """Follow-ups need their anchor on disk, so ordering is not incidental."""
    monkeypatch.chdir(tmp_path)
    order = []

    monkeypatch.setattr(
        "pipeline.anchor_jobs",
        lambda items, client=None: [("anchor", lambda: order.append("anchor"))],
    )
    monkeypatch.setattr(
        "pipeline.followup_jobs",
        lambda items, client=None: [("followup", lambda: order.append("followup"))],
    )
    monkeypatch.setattr("pipeline.audio_jobs", lambda items, client=None: [])
    monkeypatch.setattr("pipeline.missing_media", lambda items: [])

    pipeline.generate_media_stage(one_item(), log=lambda message: None)
    assert order == ["anchor", "followup"]


def test_media_stage_reports_every_asset_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = []
    monkeypatch.setattr(
        "pipeline.anchor_jobs", lambda items, client=None: [("a", lambda: None)]
    )
    monkeypatch.setattr(
        "pipeline.followup_jobs",
        lambda items, client=None: [("f1", lambda: None), ("f2", lambda: None)],
    )
    monkeypatch.setattr(
        "pipeline.audio_jobs", lambda items, client=None: [("audio", lambda: None)]
    )
    monkeypatch.setattr("pipeline.missing_media", lambda items: [])

    pipeline.generate_media_stage(
        one_item(), log=lambda message: None, on_asset=lambda r: seen.append(r.label)
    )
    assert sorted(seen) == ["a", "audio", "f1", "f2"]
```

`one_item()` is the existing helper at `tests/test_pipeline.py:12`; add `import pipeline` at the top if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `AttributeError: <module 'pipeline'> does not have the attribute 'anchor_jobs'`.

- [ ] **Step 3: Rewrite the stage**

In `pipeline.py`, change the import:

```python
from scripts.ai.generate_images.generate_images import anchor_jobs, followup_jobs
```

Replace the body of `generate_media_stage` below its docstring:

```python
    ensure_output_dirs()
    total = media_job_total(items)
    log(
        f"Generating {total} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    # One shared pool across both waves, so every stage stays under one cap.
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        # Wave one: every item's anchor frame, plus all the narration. Audio
        # rides along here rather than idling while the anchors are drawn.
        results = run_all(
            executor,
            anchor_jobs(items, client=client) + audio_jobs(items, client=client),
            on_done=on_asset,
        )
        # Wave two: the follow-up frames, each continuing an anchor that now
        # exists on disk. Built after wave one so a failed anchor is visible.
        results += run_all(
            executor, followup_jobs(items, client=client), on_done=on_asset
        )

    failures = describe_failures(results)
    if failures:
        log(failures)

    missing = missing_media(items)
    if missing:
        _fail("Media generation", missing)
```

Also update `missing_media` and `missing_titled_images` to say `beat_number` instead of `prompt_number` — they iterate `range(1, len(item.image_prompts) + 1)`, which is still correct, so this is a rename for readability only.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole Python suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "feat: run the media stage as an anchor wave then a follow-up wave"
```

---

### Task 7: Time each frame to the narration it illustrates

**Files:**
- Modify: `scripts/non_ai/generate_video_short/utils.py` (`segment_bounds`, `build_item_clip`)
- Modify: `scripts/non_ai/generate_video_short/generate_video_short.py:29-32`
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: `Item.beats` (Task 2).
- Produces:
  - `segment_bounds(total_duration: float, weights: Sequence[float] | int) -> list[tuple[float, float]]` — an int means that many equal segments.
  - `beat_weights(item: Item) -> list[float]` — word count per beat; all zeros for narrationless items.
  - `build_item_clip(item_number: int, item: Item)` — takes the item, not a count.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_video.py` (the five existing `segment_bounds` tests stay exactly as they are — passing an int must keep working):

```python
from models import Beat
from scripts.non_ai.generate_video_short.utils import beat_weights, segment_bounds, zoom_scale


def test_segment_bounds_accepts_equal_weights_like_a_count():
    assert segment_bounds(9.0, [1, 1, 1]) == segment_bounds(9.0, 3)


def test_segment_bounds_splits_proportionally_to_the_weights():
    bounds = segment_bounds(10.0, [1, 4])
    assert bounds[0] == (0.0, pytest.approx(2.0))
    assert bounds[1] == (pytest.approx(2.0), pytest.approx(8.0))


def test_segment_bounds_still_covers_the_whole_duration_when_weighted():
    start, duration = segment_bounds(10.0, [3, 1, 5, 2])[-1]
    assert start + duration == pytest.approx(10.0)


def test_segment_bounds_falls_back_to_equal_when_every_weight_is_zero():
    # Archives written before storyboards have no narration to weigh.
    assert segment_bounds(9.0, [0, 0, 0]) == segment_bounds(9.0, 3)


def test_segment_bounds_rejects_no_weights():
    with pytest.raises(ValueError):
        segment_bounds(5.0, [])


def test_beat_weights_counts_narration_words():
    item = Item(
        "T", "d",
        (Beat("one two three", "p1"), Beat("four", "p2")),
    )
    assert beat_weights(item) == [3.0, 1.0]


def test_beat_weights_are_all_zero_for_legacy_items():
    assert beat_weights(Item.from_prompts("T", "d", ("a", "b"))) == [0.0, 0.0]
```

Also update the `@pytest.mark.slow` render test at `tests/test_video.py:76` — it builds the item and then loops `range(1, 4)` writing titled images; the item is now built with `Item.from_prompts` (done in Task 2) and the frames it writes must use the new `beat_NN` filename, which `titled_image_path` already handles.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_video.py -v -m "not slow"`
Expected: FAIL with `ImportError: cannot import name 'beat_weights'`.

- [ ] **Step 3: Implement the weighted split**

In `scripts/non_ai/generate_video_short/utils.py`, replace `segment_bounds` and add `beat_weights`:

```python
def beat_weights(item: Item) -> list[float]:
    """How long each beat should hold, as the word count of its narration.

    TTS pace is close enough to uniform that word count is a good proxy for
    elapsed time, and it costs nothing. Items with no narration — every
    archive written before storyboards — weigh zero and fall back to an
    equal split.
    """
    return [float(len(beat.narration.split())) for beat in item.beats]


def segment_bounds(
    total_duration: float, weights: Sequence[float] | int
) -> list[tuple[float, float]]:
    """Split `total_duration` into (start, duration) pairs.

    `weights` may be a count, meaning that many equal segments, or a per-
    segment weight list. Equal weights produce exactly the even split, so a
    narrationless item behaves as it always did.
    """
    if isinstance(weights, int):
        weights = [1.0] * weights

    weights = list(weights)
    if not weights:
        raise ValueError("Need at least one image per item, got 0")

    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0] * len(weights)
        total_weight = float(len(weights))

    bounds: list[tuple[float, float]] = []
    start = 0.0
    for weight in weights:
        duration = total_duration * weight / total_weight
        bounds.append((start, duration))
        start += duration
    return bounds
```

Add `from typing import Sequence` and `from models import Item` to the imports.

- [ ] **Step 4: Pass the item through**

Replace `build_item_clip` in the same file:

```python
def build_item_clip(item_number: int, item: Item):
    """One item: its story frames in sequence, over its narration."""
    audio, total_duration = build_item_audio(item_number)

    layers = [build_background_clip(total_duration)]
    for beat_number, (start, duration) in enumerate(
        segment_bounds(total_duration, beat_weights(item)), start=1
    ):
        layers.append(
            build_image_clip(
                titled_image_path(item_number, beat_number), duration, start
            )
        )

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
```

And in `scripts/non_ai/generate_video_short/generate_video_short.py`:

```python
    clips = [
        build_item_clip(item_number, item)
        for item_number, item in enumerate(items, start=1)
    ]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_video.py -v`
Expected: PASS, including the slow render.

- [ ] **Step 6: Run the whole Python suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/non_ai/generate_video_short/ tests/test_video.py
git commit -m "feat: hold each frame for as long as the narration it illustrates"
```

---

### Task 8: Carry beats over the wire

**Files:**
- Modify: `api/schemas.py:19-30` (`ItemPayload`), `:80-87` (`ArchiveItemPayload`)
- Modify: `api/archives.py:100-125` (`archive_detail`)
- Test: `tests/api/test_routes.py`, `tests/api/test_archives.py`

**Interfaces:**
- Consumes: `Beat`, `Item` (Task 2).
- Produces:
  - `BeatPayload(narration: str, prompt: str)`
  - `ItemPayload(title, description, style="", beats=[], image_prompts=[])` with `ItemPayload.from_item(item)`.
  - `ArchiveItemPayload` gains `style: str = ""` and `beats: list[BeatPayload] = []`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_routes.py`:

```python
def test_run_detail_exposes_beats_and_style(client, monkeypatch):
    stub_stages(monkeypatch)
    response = client.post("/api/runs", json={"topic": "Birds", "num_items": 1})
    client.app.state.run_store.wait_for_idle()
    detail = client.get(f"/api/runs/{response.json()['id']}").json()
    item = detail["items"][0]
    assert "style" in item
    assert item["beats"][0]["prompt"] == item["image_prompts"][0]


def test_approving_storyboard_items_derives_the_description(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    client.app.state.run_store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/items",
        json={
            "items": [
                {
                    "title": "Moa",
                    "description": "stale text the server must ignore",
                    "style": "A tall bird.",
                    "beats": [
                        {"narration": "A very tall bird.", "prompt": "the bird alone"},
                        {"narration": "It could not fly.", "prompt": "the same bird, wings out"},
                    ],
                }
            ]
        },
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["description"] == "A very tall bird. It could not fly."
    assert item["image_prompts"] == ["the bird alone", "the same bird, wings out"]
```

These use the file's existing `client` fixture (`tests/api/test_routes.py:43`) and its `stub_stages(monkeypatch)` helper, reaching the store through `client.app.state.run_store` exactly as the surrounding tests do. `stub_stages` returns `one_item()`, which Task 2 rewrote to `Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))` — a legacy-shape item whose beats carry empty narration, so the first test asserts only that the fields are present and consistent.

Add to `tests/api/test_archives.py`, alongside the existing legacy-shape archive test:

```python
def test_archive_detail_exposes_beats(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = Path("generated_data/birds")
    folder.mkdir(parents=True)
    (folder / "list_items.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Moa",
                        "style": "A tall bird.",
                        "beats": [
                            {"narration": "A very tall bird.", "prompt": "the bird alone"}
                        ],
                    }
                ]
            }
        )
    )
    detail = archive_detail("birds")
    assert detail["items"][0]["style"] == "A tall bird."
    assert detail["items"][0]["beats"][0]["narration"] == "A very tall bird."
    assert detail["items"][0]["image_prompts"] == ["the bird alone"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/api -v`
Expected: FAIL — `KeyError: 'style'`.

- [ ] **Step 3: Extend the payloads**

In `api/schemas.py`, replace `ItemPayload` and add `BeatPayload` above it:

```python
class BeatPayload(BaseModel):
    narration: str
    prompt: str


class ItemPayload(BaseModel):
    """One item on the wire.

    `description` is output-only: `parse_items` recomputes it from the beat
    narrations, so a client that edits a narration cannot leave a stale script
    behind. `image_prompts` is kept so a client holding an item in the
    pre-storyboard shape can still submit it.
    """

    title: str
    description: str = ""
    style: str = ""
    beats: list[BeatPayload] = Field(default_factory=list)
    image_prompts: list[str] = Field(default_factory=list)

    @classmethod
    def from_item(cls, item: Item) -> "ItemPayload":
        return cls(
            title=item.title,
            description=item.description,
            style=item.style,
            beats=[
                BeatPayload(narration=beat.narration, prompt=beat.prompt)
                for beat in item.beats
            ],
            image_prompts=list(item.image_prompts),
        )
```

And extend `ArchiveItemPayload`:

```python
class ArchiveItemPayload(BaseModel):
    title: str
    description: str
    style: str = ""
    beats: list[BeatPayload] = Field(default_factory=list)
    image_prompts: list[str]
    image_urls: list[str]
    titled_image_urls: list[str]
    audio_url: str | None = None
```

- [ ] **Step 4: Emit beats from the archive reader**

In `api/archives.py`, inside the `payload_items.append({...})` call in `archive_detail`, add two keys next to `"image_prompts"`:

```python
                "style": item.style,
                "beats": [
                    {"narration": beat.narration, "prompt": beat.prompt}
                    for beat in item.beats
                ],
```

- [ ] **Step 5: Run the API tests**

Run: `pytest tests/api -v`
Expected: PASS. The three existing tests that post legacy `image_prompts` items still pass, because an empty `beats` list falls through to `image_prompts` in `_parse_beats`.

- [ ] **Step 6: Run the whole Python suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/ tests/api/
git commit -m "feat: carry story beats and the style sheet over the API"
```

---

### Task 9: Edit beats in the review UI

**Files:**
- Modify: `frontend/src/lib/types.ts:31-35` (`ItemPayload`)
- Modify: `frontend/src/components/ItemEditor.tsx` (whole file)
- Test: `frontend/src/components/ItemEditor.test.tsx`

**Interfaces:**
- Consumes: the wire contract from Task 8.
- Produces: `Beat` and the extended `ItemPayload` in `types.ts`.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/ItemEditor.test.tsx`'s fixture and its two prompt tests:

```tsx
const items = [
  {
    title: "Dodo",
    description: "A bird. It could not fly.",
    style: "A round flightless bird.",
    beats: [
      { narration: "A bird.", prompt: "a" },
      { narration: "It could not fly.", prompt: "b" },
    ],
    image_prompts: ["a", "b"],
  },
  {
    title: "Moa",
    description: "A taller bird.",
    style: "A very tall bird.",
    beats: [{ narration: "A taller bird.", prompt: "c" }],
    image_prompts: ["c"],
  },
];
```

```tsx
  it("adds and removes beats", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    await userEvent.click(screen.getAllByRole("button", { name: /add beat/i })[1]);
    await userEvent.type(screen.getByLabelText("Item 2 beat 2 drawing"), "new prompt");
    await userEvent.click(
      screen.getByRole("button", { name: "Remove item 1 beat 2" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].beats).toHaveLength(1);
    expect(body.items[0].beats[0].prompt).toBe("a");
    expect(body.items[1].beats[1].prompt).toBe("new prompt");
  });

  it("edits a beat's narration and shows the derived description", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    const narration = screen.getByLabelText("Item 1 beat 1 narration");
    await userEvent.clear(narration);
    await userEvent.type(narration, "A very odd bird.");

    expect(
      screen.getByText("A very odd bird. It could not fly."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].beats[0].narration).toBe("A very odd bird.");
  });

  it("edits the style sheet", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    const style = screen.getByLabelText("Item 1 style");
    await userEvent.clear(style);
    await userEvent.type(style, "A spotted bird.");
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].style).toBe("A spotted bird.");
  });
```

The existing `posts the edited items`, `removes an item` and `shows the server's rejection message` tests stay as they are.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Unable to find a label with the text of: Item 1 style`.

- [ ] **Step 3: Update the wire mirror**

In `frontend/src/lib/types.ts`, replace `ItemPayload`:

```ts
export interface Beat {
  narration: string;
  prompt: string;
}

export interface ItemPayload {
  title: string;
  /** Server-derived from the beat narrations; sent back but ignored on write. */
  description: string;
  style: string;
  beats: Beat[];
  image_prompts: string[];
}
```

- [ ] **Step 4: Rewrite the editor's item body**

In `frontend/src/components/ItemEditor.tsx`, replace the `draft` initialiser, the three prompt helpers and the description/prompt JSX. Everything else — `updateItem`, `removeItem`, `onApprove`, the error alert, the approve button — is unchanged.

```tsx
  const [draft, setDraft] = useState<ItemPayload[]>(() =>
    items.map((item) => ({
      ...item,
      beats: item.beats.length
        ? item.beats.map((beat) => ({ ...beat }))
        : item.image_prompts.map((prompt) => ({ narration: "", prompt })),
    })),
  );
```

```tsx
  const updateBeat = (index: number, beatIndex: number, patch: Partial<Beat>) =>
    updateItem(index, {
      beats: draft[index].beats.map((beat, position) =>
        position === beatIndex ? { ...beat, ...patch } : beat,
      ),
    });

  const addBeat = (index: number) =>
    updateItem(index, {
      beats: [...draft[index].beats, { narration: "", prompt: "" }],
    });

  const removeBeat = (index: number, beatIndex: number) =>
    updateItem(index, {
      beats: draft[index].beats.filter((_, position) => position !== beatIndex),
    });

  /** Mirrors the server: the script is the beat narrations, joined. */
  const derivedDescription = (item: ItemPayload) =>
    item.beats
      .map((beat) => beat.narration.trim())
      .filter(Boolean)
      .join(" ") || item.description;
```

Replace the description `<Textarea>` block and the whole `item.image_prompts.map(...)` block with:

```tsx
            <div className="space-y-1">
              <Label htmlFor={`style-${index}`}>Item {index + 1} style</Label>
              <Textarea
                id={`style-${index}`}
                value={item.style}
                onChange={(event) => updateItem(index, { style: event.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                The recurring figure and setting, redrawn in every frame.
              </p>
            </div>

            <div className="space-y-1">
              <Label>Item {index + 1} narration</Label>
              <p className="text-sm">{derivedDescription(item)}</p>
              <p className="text-xs text-muted-foreground">
                Derived from the beats below. Edit a beat to change it.
              </p>
            </div>

            <div className="space-y-3">
              {item.beats.map((beat, beatIndex) => (
                <div key={beatIndex} className="space-y-1 rounded border p-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`narration-${index}-${beatIndex}`}>
                      Item {index + 1} beat {beatIndex + 1} narration
                    </Label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove item ${index + 1} beat ${beatIndex + 1}`}
                      onClick={() => removeBeat(index, beatIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                  <Input
                    id={`narration-${index}-${beatIndex}`}
                    value={beat.narration}
                    onChange={(event) =>
                      updateBeat(index, beatIndex, { narration: event.target.value })
                    }
                  />
                  <Label htmlFor={`prompt-${index}-${beatIndex}`}>
                    Item {index + 1} beat {beatIndex + 1} drawing
                  </Label>
                  <Input
                    id={`prompt-${index}-${beatIndex}`}
                    value={beat.prompt}
                    onChange={(event) =>
                      updateBeat(index, beatIndex, { prompt: event.target.value })
                    }
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => addBeat(index)}
              >
                Add beat
              </Button>
            </div>
```

Add `Beat` to the type import: `import type { Beat, ItemPayload } from "@/lib/types";`

- [ ] **Step 5: Run the frontend tests**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npm run build`
Expected: no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/ItemEditor.tsx frontend/src/components/ItemEditor.test.tsx
git commit -m "feat: review storyboards beat by beat"
```

---

### Task 10: Show beats in the archive browser, and update the docs

**Files:**
- Modify: `frontend/src/lib/types.ts` (`ArchiveItem`)
- Modify: `frontend/src/pages/ArchiveDetailPage.tsx:86-92` (the prompt list)
- Modify: `README.md:5-22` (Overview and pipeline steps)
- Test: `frontend/src/pages/ArchiveDetailPage.test.tsx`

**Interfaces:**
- Consumes: `ArchiveItemPayload` from Task 8, `Beat` from Task 9.
- Produces: nothing downstream.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/ArchiveDetailPage.test.tsx`, following the fetch-mocking pattern already in that file:

```tsx
  it("pairs each beat's narration with its drawing prompt", async () => {
    mockJson({
      slug: "birds",
      video_url: null,
      items: [
        {
          title: "Moa",
          description: "A very tall bird. It could not fly.",
          style: "A tall bird.",
          beats: [
            { narration: "A very tall bird.", prompt: "the bird alone" },
            { narration: "It could not fly.", prompt: "the same bird, wings out" },
          ],
          image_prompts: ["the bird alone", "the same bird, wings out"],
          image_urls: [],
          titled_image_urls: [],
          audio_url: null,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("A very tall bird.")).toBeInTheDocument();
    expect(screen.getByText("the same bird, wings out")).toBeInTheDocument();
  });

  it("falls back to the flat prompt list for pre-storyboard archives", async () => {
    mockJson({
      slug: "birds",
      video_url: null,
      items: [
        {
          title: "Dodo",
          description: "A bird.",
          style: "",
          beats: [],
          image_prompts: ["a dodo", "a dodo on a skateboard"],
          image_urls: [],
          titled_image_urls: [],
          audio_url: null,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("a dodo on a skateboard")).toBeInTheDocument();
  });
```

These use the file's existing `mockJson(body)` and `renderPage()` helpers (`frontend/src/pages/ArchiveDetailPage.test.tsx:7` and `:16`), which stub `fetch` and mount the page under a `MemoryRouter` at `/archives/birds`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- ArchiveDetailPage`
Expected: FAIL — the narration text is not rendered.

- [ ] **Step 3: Extend the archive type**

In `frontend/src/lib/types.ts`, add to `ArchiveItem`:

```ts
  style: string;
  beats: Beat[];
```

- [ ] **Step 4: Render beats with a legacy fallback**

In `frontend/src/pages/ArchiveDetailPage.tsx`, replace the `<ul>` of `item.image_prompts`:

```tsx
            {item.beats.length > 0 ? (
              <ol className="space-y-1 text-xs text-muted-foreground">
                {item.beats.map((beat, beatIndex) => (
                  <li key={beatIndex}>
                    <span className="text-foreground">{beat.narration}</span>{" "}
                    {beat.prompt}
                  </li>
                ))}
              </ol>
            ) : (
              <ul className="list-disc pl-5 text-xs text-muted-foreground">
                {item.image_prompts.map((prompt, promptIndex) => (
                  <li key={promptIndex}>{prompt}</li>
                ))}
              </ul>
            )}
```

- [ ] **Step 5: Run the frontend suite and typecheck**

Run: `cd frontend && npm test && npm run build`
Expected: PASS, no TypeScript errors.

- [ ] **Step 6: Update the README**

Replace the Overview paragraph and pipeline steps 1–2 in `README.md`:

```markdown
This project automatically generates YouTube Shorts-style videos based on a topic you provide. It uses OpenAI APIs to write a narrated story for each item, draw the sequence of simple line drawings that illustrates it, and assemble them into a vertical video suitable for YouTube Shorts.

**Pipeline steps:**

1. Generate a validated list of items via JSON-schema structured outputs. Each
   item carries a style sheet naming its recurring figure, and a sequence of
   story beats pairing one sentence of narration with the drawing for it.
2. Generate every image and voiceover in two waves, capped at
   `MAX_CONCURRENT_REQUESTS` concurrent API calls: first each item's opening
   frame and its narration, then the remaining frames, each drawn as a
   continuation of that opening frame so the figure stays recognisable.
```

And in the configuration table, replace the `IMAGE_PROMPTS_PER_ITEM` row if present and add:

```markdown
| `IMAGE_PROMPTS_PER_ITEM` | `3` | Story beats per item. Sets the frame count and, at one sentence per beat, the narration length. |
| `STORYBOARD_STYLE` | stick-figure line art | The drawing style every frame shares. |
```

- [ ] **Step 7: Run everything**

Run: `pytest -q && cd frontend && npm test && npm run build`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add frontend/ README.md
git commit -m "feat: show story beats in the archive browser and document the pipeline"
```
