# Auto YouTube Generator — Refactor & Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead code, fix six latent bugs, cut pipeline wall-clock time by parallelizing all OpenAI calls and removing per-frame LANCZOS resizing, and replace stringly-typed JSON passing with typed objects — behind a pytest suite that covers every pure function.

**Architecture:** The pipeline keeps its current six stages and its `scripts/ai` + `scripts/non_ai` directory layout. Three new modules sit underneath: `config.py` (every tunable constant, env-overridable), `models.py` (an `Item` dataclass plus parse/validate, replacing JSON strings passed between stages), and `utils/openai_support.py` (one shared retry policy + one bounded thread pool helper). A new `pipeline.py` owns orchestration: it creates a single `ThreadPoolExecutor`, submits image and audio jobs into it together, and validates that every expected file exists on disk before handing off to the video renderer. `main.py` becomes a thin CLI.

**Tech Stack:** Python 3.13, openai 1.85, tenacity 9.1, moviepy 1.0.3 (pinned — not migrating), Pillow 11.2, numpy 2.3, pytest.

**Spec:** This document. Requirements were gathered in-conversation on 2026-08-17; the four scoping decisions are recorded under Global Constraints.

## Global Constraints

- **moviepy stays pinned at `moviepy==1.0.3`.** Do not migrate to 2.x. Keep the `moviepy.editor` import path and the `.set_*` method names.
- **`decorator==4.4.2` must stay installed** — moviepy 1.0.3 requires exactly this version.
- **No test may make a real network call.** Every OpenAI interaction is tested through an injected fake client. Tests must pass with `OPENAI_API_KEY` unset.
- **Model IDs live only in `config.py`.** No model string may appear anywhere else in the codebase.
- **Default concurrency is 4** (`MAX_CONCURRENT_REQUESTS`). Never unbounded.
- **Output filenames must not change.** `item_01_prompt_02.png`, `item_01.mp3`, `item_01_prompt_02_short.png`, `final_video_short.mp4`. Existing folders under `generated_data/` must remain readable.
- **Video geometry stays 1080×1920 @ 24fps.**
- **Commit after every task.** Conventional-commit prefixes (`chore:`, `fix:`, `feat:`, `refactor:`, `test:`, `perf:`, `docs:`).

---

## File Structure

**Deleted outright:**
- `zaza_book/` — unrelated story-generator side project, untracked in git
- `auto_youtube_generator/` — contains nothing but `__pycache__` from a previous directory layout
- `__pycache__/` (repo root) — stale bytecode for modules that no longer exist
- `outputs/list_output/` — nothing in the codebase writes here
- `utils/helper_functions.py` — `clean_json_input` becomes unnecessary once structured outputs land
- `utils/output_dirs.py`, `utils/output_file_names.py` — merged into `utils/paths.py`

**Created:**
| File | Responsibility |
|---|---|
| `config.py` | Every tunable constant. Env-var overridable. No logic beyond parsing/validating env vars. |
| `models.py` | The `Item` dataclass; parsing, validating, loading and saving item lists. |
| `utils/paths.py` | All output directory constants and filename builders. Merges the two old path modules. |
| `utils/openai_support.py` | Shared tenacity retry policy + bounded-parallelism helper. |
| `pipeline.py` | Stage orchestration, the shared thread pool, and between-stage asset validation. |
| `pytest.ini` | Puts the repo root on `sys.path` so tests can `import config`. |
| `.env.example` | Documents required and optional env vars. |
| `tests/` | Nine test modules, one per unit under test. |

**Modified:** `main.py`, `requirements.txt`, `.gitignore`, `README.md`, and all five stage modules under `scripts/`.

---

### Task 1: Repo cleanup and a working environment

Nothing else can be verified until the venv runs and the dead directories are gone. `requirements.txt` is currently missing `python-dotenv`, which the code imports — a fresh clone following the README crashes on the first run.

**Files:**
- Delete: `zaza_book/`, `auto_youtube_generator/`, `__pycache__/`, `outputs/list_output/`
- Modify: `.gitignore`, `requirements.txt`
- Create: `.env.example`, `pytest.ini`

- [x] **Step 1: Confirm `zaza_book/` and `auto_youtube_generator/` hold nothing tracked**

```bash
git ls-files zaza_book auto_youtube_generator
```

Expected: no output at all. If anything prints, stop and report it before deleting.

- [x] **Step 2: Delete the dead directories**

```bash
rm -rf zaza_book auto_youtube_generator __pycache__ outputs/list_output
find . -path ./venv -prune -o -name "__pycache__" -type d -print -exec rm -rf {} +
```

- [x] **Step 3: Stop tracking `.DS_Store` and ignore it**

```bash
git rm --cached .DS_Store
printf '\n# macOS\n.DS_Store\n' >> .gitignore
```

- [x] **Step 4: Fix `requirements.txt`**

`python-dotenv` is imported by `utils/open_ai_client.py` but was never declared. `numpy` is imported directly by the video code and must be declared explicitly rather than relied on transitively through moviepy. `decorator` is pinned because moviepy 1.0.3 breaks on newer versions.

Replace the entire file with:

```
openai>=1.85.0
tenacity>=9.0.0
python-dotenv>=1.0.0
moviepy==1.0.3
decorator==4.4.2
numpy>=1.24.0
pillow>=10.0.0
pytest>=8.0.0
```

- [x] **Step 5: Create `.env.example`**

```
# Required
OPENAI_API_KEY=sk-your-key-here

# Optional overrides (defaults shown, see config.py)
# TEXT_MODEL=gpt-4.1-mini
# TTS_MODEL=gpt-4o-mini-tts
# TTS_VOICE=ash
# IMAGE_MODEL=gpt-image-1
# IMAGE_QUALITY=medium
# MAX_CONCURRENT_REQUESTS=4
# MAX_RETRIES=5
# VIDEO_FPS=24
# VIDEO_PRESET=medium
```

- [x] **Step 6: Create `pytest.ini`**

The `pythonpath` option makes `import config` and `from utils.paths import ...` resolve from the repo root without installing the project as a package.

```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -q
```

- [x] **Step 7: Rebuild the virtualenv**

The existing `venv/bin/python` symlink is dangling — `./venv/bin/python -c "print(1)"` fails with "no such file or directory". Rebuild it:

```bash
rm -rf venv
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements.txt
```

Use `python3.12` (moviepy 1.0.3 and numpy have the widest wheel coverage there). If `python3.12` is unavailable, `python3.13` is acceptable.

- [x] **Step 8: Verify the environment imports cleanly**

```bash
./venv/bin/python -c "
import openai, moviepy.editor, PIL, tenacity, numpy, dotenv, pytest
print('openai', openai.__version__)
print('all imports OK')
"
```

Expected: `all imports OK`. `moviepy.editor` is the slow one — if it hangs for 10s on first import that is normal (it probes for ffmpeg).

- [x] **Step 9: Create the tests directory with a placeholder so pytest has a target**

Create `tests/__init__.py` as an empty file.

- [x] **Step 10: Verify pytest runs**

```bash
./venv/bin/pytest
```

Expected: `no tests ran` — exit code 5. That is the correct outcome; there are no tests yet.

- [x] **Step 11: Commit**

```bash
git add -A
git commit -m "chore: remove dead directories, fix requirements, add test harness"
```

---

### Task 2: `config.py` and `utils/paths.py`

Right now `MAX_RETRIES` and `DELAY_BETWEEN_REQUESTS` are each defined in four separate files, model IDs are buried in call sites, and geometry numbers like `1080` and `1920` are scattered across three modules. Path building is split across `output_dirs.py` and `output_file_names.py`, and several call sites bypass both and hardcode the filename pattern inline.

**Files:**
- Create: `config.py`, `utils/paths.py`, `tests/test_config.py`, `tests/test_paths.py`
- Delete: `utils/output_dirs.py`, `utils/output_file_names.py`

**Interfaces:**
- Produces: `config.<CONSTANT>` for every constant listed below. `utils.paths` exports `AUDIO_OUTPUT_DIR`, `IMAGE_OUTPUT_DIR`, `JSON_OUTPUT_DIR`, `TITLED_IMAGE_OUTPUT_DIR`, `VIDEO_OUTPUT_DIR`, `GENERATED_DATA_ROOT` (all `pathlib.Path`), plus `ensure_output_dirs() -> None`, `image_path(int, int) -> Path`, `audio_path(int) -> Path`, `titled_image_path(int, int) -> Path`, `list_items_path() -> Path`, `video_output_path() -> Path`, `slugify(str) -> str`, `generated_data_dir(str) -> Path`.

- [x] **Step 1: Write the failing tests for `config.py`**

Create `tests/test_config.py`:

```python
import importlib

import pytest

import config


def reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


def test_defaults_are_sane():
    module = importlib.reload(config)
    assert module.IMAGE_PROMPTS_PER_ITEM == 3
    assert module.MAX_CONCURRENT_REQUESTS == 4
    assert module.VIDEO_WIDTH == 1080
    assert module.VIDEO_HEIGHT == 1920
    assert module.VIDEO_FPS == 24
    assert module.ZOOM_END_SCALE == pytest.approx(1.2)


def test_int_env_override(monkeypatch):
    module = reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="9")
    assert module.MAX_CONCURRENT_REQUESTS == 9


def test_str_env_override(monkeypatch):
    module = reload_config(monkeypatch, TEXT_MODEL="my-model")
    assert module.TEXT_MODEL == "my-model"


def test_blank_env_falls_back_to_default(monkeypatch):
    module = reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="   ")
    assert module.MAX_CONCURRENT_REQUESTS == 4


def test_non_numeric_env_raises(monkeypatch):
    with pytest.raises(ValueError, match="MAX_CONCURRENT_REQUESTS"):
        reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="four")


def test_non_positive_env_raises(monkeypatch):
    with pytest.raises(ValueError, match="MAX_CONCURRENT_REQUESTS"):
        reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="0")


@pytest.fixture(autouse=True)
def restore_config():
    yield
    importlib.reload(config)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [x] **Step 3: Write `config.py`**

```python
"""Single source of truth for every tunable constant in the pipeline.

Each value may be overridden by an environment variable of the same name, so
you can experiment (different model, higher concurrency, faster encode) without
editing code. Values are read at import time.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be a whole number, got {raw!r}"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"Environment variable {name} must be greater than zero, got {value}"
        )
    return value


# --- OpenAI models -------------------------------------------------------
# gpt-4.1-mini supports JSON schema structured outputs, which is what lets us
# drop the old markdown-fence-stripping hack.
TEXT_MODEL = _env_str("TEXT_MODEL", "gpt-4.1-mini")
TEXT_TEMPERATURE = 0.7

# gpt-4o-mini-tts is the model that actually honours the `instructions`
# parameter. The old tts-1 silently ignored it.
TTS_MODEL = _env_str("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = _env_str("TTS_VOICE", "ash")
TTS_INSTRUCTIONS = (
    "Speak in an engaging tone that would be informative and interesting for a "
    "YouTube video. Use a professional, conversational style."
)

IMAGE_MODEL = _env_str("IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = _env_str("IMAGE_SIZE", "1024x1024")
IMAGE_QUALITY = _env_str("IMAGE_QUALITY", "medium")

# --- Pipeline shape ------------------------------------------------------
IMAGE_PROMPTS_PER_ITEM = _env_int("IMAGE_PROMPTS_PER_ITEM", 3)
MAX_CONCURRENT_REQUESTS = _env_int("MAX_CONCURRENT_REQUESTS", 4)
MAX_RETRIES = _env_int("MAX_RETRIES", 5)
RETRY_INITIAL_WAIT_SECONDS = 2.0
RETRY_MAX_WAIT_SECONDS = 60.0

# --- Video geometry (YouTube Shorts, 9:16) -------------------------------
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = _env_int("VIDEO_FPS", 24)
VIDEO_CODEC = "libx264"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_PRESET = _env_str("VIDEO_PRESET", "medium")
INTRO_SILENCE_SECONDS = 0.2
OUTRO_SILENCE_SECONDS = 0.5
ZOOM_END_SCALE = 1.2

# --- Titled image rendering ---------------------------------------------
TITLE_FONT_SIZE = 120
TITLE_LINE_SPACING = 10
TITLE_SIDE_MARGIN = 50
TITLE_GAP_BELOW_IMAGE = 220
TITLE_COLOR = "black"
BACKGROUND_BLUR_RADIUS = 90
# The background blur is applied at 1/N scale and upscaled back. For a radius
# this large the result is visually identical and ~100x cheaper.
BLUR_DOWNSCALE_FACTOR = 10
BACKGROUND_OVERLAY_ALPHA = 128
```

- [x] **Step 4: Run the config tests to verify they pass**

Run: `./venv/bin/pytest tests/test_config.py -v`
Expected: PASS, 6 passed

- [x] **Step 5: Write the failing tests for `utils/paths.py`**

Note `test_slugify_collapses_runs` — the current implementation in `save_to_generated_data.py` turns `"Top 5: Extinct Animals!"` into `"top_5__extinct_animals_"` with a doubled and a trailing underscore. `test_slugify_matches_existing_folders` locks in backwards compatibility with the four folders already in `generated_data/`.

Create `tests/test_paths.py`:

```python
from pathlib import Path

import pytest

from utils import paths


def test_image_path_is_zero_padded():
    assert paths.image_path(1, 2) == Path("outputs/image_output/item_01_prompt_02.png")


def test_image_path_handles_double_digits():
    assert paths.image_path(12, 10) == Path("outputs/image_output/item_12_prompt_10.png")


def test_audio_path_is_zero_padded():
    assert paths.audio_path(3) == Path("outputs/audio_output/item_03.mp3")


def test_titled_image_path_has_short_suffix():
    assert paths.titled_image_path(5, 1) == Path(
        "outputs/titled_image_output/item_05_prompt_01_short.png"
    )


def test_list_items_path():
    assert paths.list_items_path() == Path(
        "outputs/json_output/list_items_with_prompts.json"
    )


def test_video_output_path():
    assert paths.video_output_path() == Path("outputs/video_output/final_video_short.mp4")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Top 5 Extinct Animals", "top_5_extinct_animals"),
        ("Most Delicious Sandwiches", "most_delicious_sandwiches"),
        ("Top 5: Extinct Animals!", "top_5_extinct_animals"),
        ("  spaced   out  ", "spaced_out"),
        ("!!!", "untitled"),
        ("", "untitled"),
    ],
)
def test_slugify(raw, expected):
    assert paths.slugify(raw) == expected


def test_generated_data_dir():
    assert paths.generated_data_dir("Top 5 Extinct Animals") == Path(
        "generated_data/top_5_extinct_animals"
    )


def test_ensure_output_dirs_creates_everything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths.ensure_output_dirs()
    for directory in paths.ALL_OUTPUT_DIRS:
        assert directory.is_dir()


def test_ensure_output_dirs_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths.ensure_output_dirs()
    paths.ensure_output_dirs()
    assert paths.AUDIO_OUTPUT_DIR.is_dir()
```

- [x] **Step 6: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_paths.py -v`
Expected: FAIL — `ImportError: cannot import name 'paths' from 'utils'`

- [x] **Step 7: Write `utils/paths.py`**

All paths are relative to the process working directory, which is the repo root. They are kept relative (not resolved to absolute at import time) so that tests can `monkeypatch.chdir(tmp_path)` and exercise real filesystem behaviour in isolation.

```python
"""Every output directory and filename the pipeline produces.

Paths are deliberately relative to the current working directory so tests can
chdir into a temp directory and exercise real filesystem behaviour.
"""

import re
from pathlib import Path

OUTPUTS_ROOT = Path("outputs")
AUDIO_OUTPUT_DIR = OUTPUTS_ROOT / "audio_output"
IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "image_output"
JSON_OUTPUT_DIR = OUTPUTS_ROOT / "json_output"
TITLED_IMAGE_OUTPUT_DIR = OUTPUTS_ROOT / "titled_image_output"
VIDEO_OUTPUT_DIR = OUTPUTS_ROOT / "video_output"

GENERATED_DATA_ROOT = Path("generated_data")

ALL_OUTPUT_DIRS = (
    AUDIO_OUTPUT_DIR,
    IMAGE_OUTPUT_DIR,
    JSON_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    VIDEO_OUTPUT_DIR,
)

LIST_ITEMS_FILENAME = "list_items_with_prompts.json"
ARCHIVED_LIST_FILENAME = "list_items.json"
VIDEO_FILENAME = "final_video_short.mp4"

_SLUG_SEPARATORS = re.compile(r"[^a-z0-9]+")


def ensure_output_dirs() -> None:
    """Create every output directory. Safe to call repeatedly."""
    for directory in ALL_OUTPUT_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def image_path(item_number: int, prompt_number: int) -> Path:
    return IMAGE_OUTPUT_DIR / f"item_{item_number:02d}_prompt_{prompt_number:02d}.png"


def audio_path(item_number: int) -> Path:
    return AUDIO_OUTPUT_DIR / f"item_{item_number:02d}.mp3"


def titled_image_path(item_number: int, prompt_number: int) -> Path:
    return (
        TITLED_IMAGE_OUTPUT_DIR
        / f"item_{item_number:02d}_prompt_{prompt_number:02d}_short.png"
    )


def list_items_path() -> Path:
    return JSON_OUTPUT_DIR / LIST_ITEMS_FILENAME


def video_output_path() -> Path:
    return VIDEO_OUTPUT_DIR / VIDEO_FILENAME


def slugify(text: str) -> str:
    """Turn a topic into a filesystem-safe folder name.

    Runs of non-alphanumeric characters collapse to a single underscore and
    leading/trailing underscores are stripped, so "Top 5: Extinct Animals!"
    becomes "top_5_extinct_animals".
    """
    slug = _SLUG_SEPARATORS.sub("_", text.lower()).strip("_")
    return slug or "untitled"


def generated_data_dir(topic: str) -> Path:
    return GENERATED_DATA_ROOT / slugify(topic)
```

- [x] **Step 8: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_paths.py -v`
Expected: PASS, 16 passed

- [x] **Step 9: Delete the two superseded modules**

The stage modules still import from them and will be updated in later tasks; that is expected and the repo will not run until Task 11. Tests keep passing throughout because they only touch the new modules.

```bash
git rm utils/output_dirs.py utils/output_file_names.py
```

- [x] **Step 10: Commit**

```bash
git add config.py utils/paths.py tests/test_config.py tests/test_paths.py
git commit -m "refactor: centralize constants in config.py and paths in utils/paths.py"
```

---

### Task 3: `models.py` — typed items instead of JSON strings

Today a JSON *string* is threaded through every stage. `main.py` calls `clean_json_input` on it, then `generate_images` calls `clean_json_input` on it *again*, and each stage re-runs `json.loads`. Nothing validates that the model returned three image prompts, so a short list surfaces as a `FileNotFoundError` inside moviepy several minutes later.

**Files:**
- Create: `models.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `config.IMAGE_PROMPTS_PER_ITEM`
- Produces: `Item` (frozen dataclass with `.title: str`, `.description: str`, `.image_prompts: tuple[str, ...]`, and the `.narration` property), `InvalidItemsError(ValueError)`, `parse_items(raw, *, expected_prompts=None) -> list[Item]`, `items_to_json(items) -> str`, `save_items(items, path) -> None`, `load_items(path) -> list[Item]`.

- [x] **Step 1: Write the failing tests**

`parse_items` must accept both shapes: the `{"items": [...]}` envelope that JSON-schema structured output returns, and a bare `[...]` list — which is what the four existing files under `generated_data/*/list_items.json` contain.

Create `tests/test_models.py`:

```python
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'`

- [x] **Step 3: Write `models.py`**

```python
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
        if not isinstance(prompts, list) or not all(
            isinstance(p, str) and p.strip() for p in prompts
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
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_models.py -v`
Expected: PASS, 17 passed

- [x] **Step 5: Verify the existing saved files still parse**

This proves backwards compatibility with the four folders already in `generated_data/`.

```bash
./venv/bin/python -c "
from pathlib import Path
from models import load_items
for p in sorted(Path('generated_data').glob('*/list_items.json')):
    items = load_items(p)
    print(f'{p}: {len(items)} items, {len(items[0].image_prompts)} prompts each')
"
```

Expected: four lines, each reporting 5 items with 3 prompts each. If any file fails to parse, fix `parse_items` — do not modify the data files.

- [x] **Step 6: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add typed Item model with validation, replacing raw JSON strings"
```

---

### Task 4: `utils/openai_support.py` — shared retry policy and bounded parallelism

Two problems solved here. First, the current `@retry(stop=stop_after_attempt(3))` retries *everything*, including `BadRequestError` — so an image prompt rejected by the content filter burns three identical doomed API calls before failing. Second, every stage sleeps a hardcoded 5 seconds after each call: for 5 items that is 15 image sleeps plus 5 audio sleeps, 100 seconds of doing nothing, on top of fully serial request latency.

**Files:**
- Create: `utils/openai_support.py`, `tests/test_openai_support.py`

**Interfaces:**
- Consumes: `config.MAX_RETRIES`, `config.RETRY_INITIAL_WAIT_SECONDS`, `config.RETRY_MAX_WAIT_SECONDS`
- Produces: `RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...]`, `with_retry(fn) -> fn` (decorator), `TaskResult` (dataclass: `.label: str`, `.value: Any`, `.error: BaseException | None`, `.ok: bool`), `run_all(executor, jobs) -> list[TaskResult]` where `jobs` is `Sequence[tuple[str, Callable[[], Any]]]`, `describe_failures(results) -> str`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_openai_support.py`:

```python
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import openai
import pytest

from utils.openai_support import (
    RETRYABLE_EXCEPTIONS,
    TaskResult,
    describe_failures,
    run_all,
    with_retry,
)


def make_api_error(cls, status_code):
    request = httpx.Request("POST", "https://api.openai.com/v1/x")
    response = httpx.Response(status_code, request=request)
    return cls("boom", response=response, body=None)


def test_rate_limit_is_retryable():
    assert openai.RateLimitError in RETRYABLE_EXCEPTIONS


def test_internal_server_error_is_retryable():
    assert openai.InternalServerError in RETRYABLE_EXCEPTIONS


def test_bad_request_is_not_retryable():
    # A content-policy rejection will never succeed on retry.
    assert openai.BadRequestError not in RETRYABLE_EXCEPTIONS


def test_with_retry_recovers_from_a_transient_error(monkeypatch):
    monkeypatch.setattr("utils.openai_support._wait_strategy", lambda: (lambda rs: 0))
    calls = []

    @with_retry
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise make_api_error(openai.RateLimitError, 429)
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_with_retry_gives_up_on_a_non_retryable_error(monkeypatch):
    monkeypatch.setattr("utils.openai_support._wait_strategy", lambda: (lambda rs: 0))
    calls = []

    @with_retry
    def rejected():
        calls.append(1)
        raise make_api_error(openai.BadRequestError, 400)

    with pytest.raises(openai.BadRequestError):
        rejected()
    assert len(calls) == 1, "a content-policy rejection must not be retried"


def test_run_all_preserves_input_order():
    jobs = [(f"job-{i}", (lambda i=i: i)) for i in range(10)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, jobs)
    assert [r.value for r in results] == list(range(10))
    assert [r.label for r in results] == [f"job-{i}" for i in range(10)]


def test_run_all_collects_errors_without_stopping():
    def explode():
        raise RuntimeError("nope")

    jobs = [("good", lambda: 1), ("bad", explode), ("also-good", lambda: 3)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = run_all(executor, jobs)

    assert [r.ok for r in results] == [True, False, True]
    assert isinstance(results[1].error, RuntimeError)
    assert results[0].value == 1
    assert results[2].value == 3


def test_run_all_actually_runs_in_parallel():
    barrier = threading.Barrier(4, timeout=5)

    def wait_for_others():
        barrier.wait()
        return True

    jobs = [(f"j{i}", wait_for_others) for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, jobs)

    # The barrier only releases if all four ran concurrently.
    assert all(r.ok for r in results)


def test_run_all_respects_the_worker_cap():
    live = 0
    peak = 0
    lock = threading.Lock()

    def track():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1

    jobs = [(f"j{i}", track) for i in range(12)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        run_all(executor, jobs)

    assert peak <= 3


def test_run_all_handles_an_empty_job_list():
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert run_all(executor, []) == []


def test_describe_failures_lists_each_failure():
    results = [
        TaskResult("image item 1 prompt 2", error=RuntimeError("filtered")),
        TaskResult("audio item 3", value="ok"),
        TaskResult("image item 4 prompt 1", error=ValueError("empty")),
    ]
    message = describe_failures(results)
    assert "image item 1 prompt 2" in message
    assert "filtered" in message
    assert "image item 4 prompt 1" in message
    assert "audio item 3" not in message


def test_describe_failures_is_empty_when_all_succeeded():
    assert describe_failures([TaskResult("a", value=1)]) == ""
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_openai_support.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.openai_support'`

- [x] **Step 3: Write `utils/openai_support.py`**

`_wait_strategy` is a function rather than a module constant purely so tests can monkeypatch it to zero and run instantly.

```python
"""Shared retry policy and bounded parallelism for OpenAI calls.

Two things live here because every stage needs both:

1. A retry policy that backs off on transient failures (rate limits, timeouts,
   5xx) but fails immediately on `BadRequestError` — a prompt rejected by the
   content filter will never succeed on retry, so retrying just wastes time.
2. A helper that submits jobs into a shared, capped thread pool and returns
   results in submission order with per-job errors captured rather than raised.
"""

from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

import config

RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


def _wait_strategy():
    return wait_exponential_jitter(
        initial=config.RETRY_INITIAL_WAIT_SECONDS,
        max=config.RETRY_MAX_WAIT_SECONDS,
    )


def with_retry(fn: Callable) -> Callable:
    """Retry `fn` on transient OpenAI failures with exponential backoff."""
    return retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(config.MAX_RETRIES),
        wait=_wait_strategy(),
        reraise=True,
    )(fn)


@dataclass
class TaskResult:
    """The outcome of one parallel job: either a value or the error it raised."""

    label: str
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


Job = tuple[str, Callable[[], Any]]


def run_all(executor: Executor, jobs: Sequence[Job]) -> list[TaskResult]:
    """Run every job on `executor`, returning results in submission order.

    A failing job does not stop the others; its exception is captured on the
    corresponding `TaskResult`. Passing a shared executor lets several stages
    interleave their work under one global concurrency cap.
    """
    submitted = [(label, executor.submit(fn)) for label, fn in jobs]

    results: list[TaskResult] = []
    for label, future in submitted:
        try:
            results.append(TaskResult(label, value=future.result()))
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            results.append(TaskResult(label, error=exc))
    return results


def describe_failures(results: Sequence[TaskResult]) -> str:
    """Render a human-readable summary of failures, or "" if there were none."""
    failures = [r for r in results if not r.ok]
    if not failures:
        return ""
    lines = [f"  - {r.label}: {type(r.error).__name__}: {r.error}" for r in failures]
    return f"{len(failures)} job(s) failed:\n" + "\n".join(lines)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_openai_support.py -v`
Expected: PASS, 12 passed

- [x] **Step 5: Commit**

```bash
git add utils/openai_support.py tests/test_openai_support.py
git commit -m "feat: add shared retry policy and bounded parallel job runner"
```

---

### Task 5: `generate_list` with JSON-schema structured outputs

`model="gpt-4"` cannot be asked for guaranteed JSON, which is why the model wraps its answer in markdown fences and `clean_json_input` exists to strip them. Switching to a model that supports `json_schema` response format makes malformed output structurally impossible and deletes that whole class of problem.

**Files:**
- Modify: `scripts/ai/generate_list/generate_list.py`
- Create: `scripts/ai/__init__.py`, `scripts/ai/generate_list/__init__.py`, `tests/test_generate_list.py`
- Delete: `utils/helper_functions.py`

**Interfaces:**
- Consumes: `config.TEXT_MODEL`, `config.TEXT_TEMPERATURE`, `config.IMAGE_PROMPTS_PER_ITEM`; `models.parse_items`, `models.Item`; `utils.openai_support.with_retry`
- Produces: `generate_list(topic: str, num_items: int, *, client=None) -> list[Item]`

- [x] **Step 1: Write the failing tests**

Create `tests/test_generate_list.py`:

```python
import json
from types import SimpleNamespace

import pytest

from models import InvalidItemsError
from scripts.ai.generate_list.generate_list import LIST_JSON_SCHEMA, generate_list


def build_payload(count=3, prompts=3):
    return {
        "items": [
            {
                "title": f"Item {i}",
                "description": f"Description {i}. Second sentence.",
                "image_prompts": [f"prompt {i}.{j}" for j in range(prompts)],
            }
            for i in range(1, count + 1)
        ]
    }


class FakeClient:
    """Records the request and replays a canned response."""

    def __init__(self, content):
        self.content = content
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_returns_typed_items():
    client = FakeClient(json.dumps(build_payload(count=3)))
    items = generate_list("extinct animals", 3, client=client)
    assert len(items) == 3
    assert items[0].title == "Item 1"
    assert len(items[0].image_prompts) == 3


def test_requests_a_strict_json_schema():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == LIST_JSON_SCHEMA


def test_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr("config.TEXT_MODEL", "test-model")
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    assert client.calls[0]["model"] == "test-model"


def test_prompt_mentions_the_topic_and_count():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "extinct animals" in user_message
    assert "3" in user_message


def test_prompt_keeps_the_safety_and_copyright_guidance():
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
    user_message = client.calls[0]["messages"][1]["content"]
    assert "family-friendly" in user_message
    assert "copyrighted" in user_message.lower()


def test_schema_root_is_an_object():
    # OpenAI strict mode requires an object at the root, not an array.
    assert LIST_JSON_SCHEMA["type"] == "object"
    assert LIST_JSON_SCHEMA["additionalProperties"] is False


def test_rejects_a_short_prompt_list():
    client = FakeClient(json.dumps(build_payload(count=1, prompts=2)))
    with pytest.raises(InvalidItemsError, match="3 image prompts"):
        generate_list("extinct animals", 1, client=client)


def test_rejects_an_empty_response():
    client = FakeClient(None)
    with pytest.raises(InvalidItemsError):
        generate_list("extinct animals", 1, client=client)


def test_rejects_a_non_positive_count():
    client = FakeClient(json.dumps(build_payload()))
    with pytest.raises(ValueError, match="at least 1"):
        generate_list("extinct animals", 0, client=client)


def test_does_not_write_to_disk():
    # Persistence is the pipeline's job, not this stage's.
    client = FakeClient(json.dumps(build_payload()))
    generate_list("extinct animals", 3, client=client)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_generate_list.py -v`
Expected: FAIL — `ImportError: cannot import name 'LIST_JSON_SCHEMA'`

- [x] **Step 3: Create the package `__init__.py` files**

Create `scripts/__init__.py`, `scripts/ai/__init__.py`, and `scripts/ai/generate_list/__init__.py` as empty files. The codebase currently relies on implicit namespace packages, which is why `generate_audio.py` can use `from .utils import ...` while `generate_video_short.py` uses a full absolute path. Explicit packages make relative imports work consistently.

- [x] **Step 4: Rewrite `scripts/ai/generate_list/generate_list.py`**

Note the schema deliberately does not constrain `image_prompts` length — OpenAI strict mode does not support `minItems`/`maxItems`, so the count is enforced in `parse_items` instead, and asked for in the prompt text.

```python
"""Ask the model for a list of video items, as guaranteed-valid JSON."""

import config
from models import Item, parse_items
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry

SYSTEM_MESSAGE = (
    "You are a helpful assistant that generates a list of interesting facts, "
    "places, or concepts, along with creative image prompts. Always ensure all "
    "content is family-friendly and appropriate for all audiences."
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
                    "description": {
                        "type": "string",
                        "description": "Two informative, intriguing sentences.",
                    },
                    "image_prompts": {
                        "type": "array",
                        "description": "Image generation prompts for this item.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "description", "image_prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _build_user_message(topic: str, num_items: int) -> str:
    prompt_count = config.IMAGE_PROMPTS_PER_ITEM
    return (
        f"Give me a list of {num_items} items for a YouTube video on the topic: "
        f"'{topic}'.\n"
        f"Each item must have:\n"
        f"1. A very short, concise title (just the main subject/name, no "
        f"additional descriptive text)\n"
        f"2. A 2 sentence description that is informative and intriguing\n"
        f"3. Exactly {prompt_count} different image_prompts that would create "
        f"engaging visuals for this item:\n"
        f"   - First prompt: A straightforward, clear representation of the "
        f"item. The prompt should just be the item name.\n"
        f"   - Second prompt: The item in a creative setting. Should be "
        f"hilariously funny and creative.\n"
        f"   - Third prompt: The item in a different style or perspective than "
        f"the first two. Should be a bit more creative and unique.\n"
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


@with_retry
def _request_items(client, topic: str, num_items: int) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": _build_user_message(topic, num_items)},
        ],
        temperature=config.TEXT_TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "video_items",
                "strict": True,
                "schema": LIST_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def generate_list(topic: str, num_items: int = 5, *, client=None) -> list[Item]:
    """Generate `num_items` validated items for `topic`.

    Raises `InvalidItemsError` if the model's output does not match the
    expected shape, including a wrong number of image prompts.
    """
    if num_items < 1:
        raise ValueError(f"num_items must be at least 1, got {num_items}")

    client = client or get_open_ai_client()
    content = _request_items(client, topic, num_items)
    return parse_items(content or "")
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_generate_list.py -v`
Expected: PASS, 10 passed

- [x] **Step 6: Delete `utils/helper_functions.py`**

`clean_json_input` has no remaining callers — its fence-stripping job now lives inside `models._strip_markdown_fences`, used only for reading legacy files.

```bash
git rm utils/helper_functions.py
grep -rn "clean_json_input\|helper_functions" --include="*.py" . --exclude-dir=venv
```

Expected from the grep: no output.

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: use JSON schema structured outputs for list generation"
```

---

### Task 6: Parallel image generation

This is the single largest wall-clock win. Fifteen images currently run strictly one at a time with a hardcoded `time.sleep(5)` after each — 75 seconds of pure sleep plus fully serial latency.

**Files:**
- Modify: `scripts/ai/generate_images/generate_images.py`, `scripts/ai/generate_images/utils.py`
- Create: `scripts/ai/generate_images/__init__.py`, `tests/test_generate_images.py`

**Interfaces:**
- Consumes: `config.IMAGE_MODEL/IMAGE_SIZE/IMAGE_QUALITY`; `models.Item`; `utils.paths.image_path`; `utils.openai_support.with_retry`, `run_all`, `Job`
- Produces: `generate_image(prompt: str, destination: Path, *, client=None) -> Path` in `utils.py`; `image_jobs(items: Sequence[Item], *, client=None) -> list[Job]` and `generate_images(items, *, client=None) -> list[TaskResult]` in `generate_images.py`

- [x] **Step 1: Write the failing tests**

`image_jobs` returning a list of un-run callables is what lets `pipeline.py` merge image and audio work into one capped pool — and it makes the fan-out testable without running anything.

Create `tests/test_generate_images.py`:

```python
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Item
from scripts.ai.generate_images.generate_images import generate_images, image_jobs
from scripts.ai.generate_images.utils import generate_image
from utils.openai_support import run_all

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeImages:
    def __init__(self, b64=None, error=None):
        self.b64 = b64
        self.error = error
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])


def fake_client(b64=None, error=None):
    images = FakeImages(b64=b64, error=error)
    return SimpleNamespace(images=images), images


def two_items():
    return [
        Item("A", "First.", ("a1", "a2", "a3")),
        Item("B", "Second.", ("b1", "b2", "b3")),
    ]


def test_generate_image_writes_the_decoded_bytes(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    destination = tmp_path / "out.png"
    result = generate_image("a dodo", destination, client=client)
    assert result == destination
    assert destination.read_bytes() == PNG_BYTES


def test_generate_image_creates_parent_directories(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    destination = tmp_path / "deep" / "nested" / "out.png"
    generate_image("a dodo", destination, client=client)
    assert destination.exists()


def test_generate_image_passes_configured_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr("config.IMAGE_MODEL", "test-image-model")
    monkeypatch.setattr("config.IMAGE_QUALITY", "high")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    generate_image("a dodo", tmp_path / "out.png", client=client)
    assert images.calls[0]["model"] == "test-image-model"
    assert images.calls[0]["quality"] == "high"
    assert images.calls[0]["prompt"] == "a dodo"
    assert images.calls[0]["n"] == 1


def test_generate_image_raises_when_no_data_returned(tmp_path):
    client, _ = fake_client(b64=None)
    with pytest.raises(ValueError, match="No image data"):
        generate_image("a dodo", tmp_path / "out.png", client=client)


def test_generate_image_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(b64=None)
    destination = tmp_path / "out.png"
    with pytest.raises(ValueError):
        generate_image("a dodo", destination, client=client)
    assert not destination.exists()


def test_image_jobs_fans_out_one_job_per_prompt():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    jobs = image_jobs(two_items(), client=client)
    assert len(jobs) == 6


def test_image_jobs_labels_identify_item_and_prompt():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    labels = [label for label, _ in image_jobs(two_items(), client=client)]
    assert labels[0] == "image item 1 prompt 1"
    assert labels[-1] == "image item 2 prompt 3"


def test_image_jobs_are_not_executed_when_built():
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    image_jobs(two_items(), client=client)
    assert images.calls == []


def test_generate_images_writes_every_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    results = generate_images(two_items(), client=client)
    assert all(r.ok for r in results)
    assert Path("outputs/image_output/item_01_prompt_01.png").exists()
    assert Path("outputs/image_output/item_02_prompt_03.png").exists()


def test_generate_images_reports_failures_without_stopping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    original = images.generate
    calls = {"n": 0}

    def sometimes_fail(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("content filtered")
        return original(**kwargs)

    images.generate = sometimes_fail
    results = generate_images(two_items(), client=client)
    assert sum(1 for r in results if not r.ok) == 1
    assert sum(1 for r in results if r.ok) == 5


def test_jobs_run_correctly_through_the_shared_runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, image_jobs(two_items(), client=client))
    assert all(r.ok for r in results)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_generate_images.py -v`
Expected: FAIL — `ImportError: cannot import name 'image_jobs'`

- [x] **Step 3: Rewrite `scripts/ai/generate_images/utils.py`**

The write is done to a temp file and then atomically renamed, so a crash mid-write cannot leave a truncated PNG that the validation step would happily accept.

```python
"""Single-image generation against the OpenAI images API."""

import base64
import os
from pathlib import Path

import config
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


@with_retry
def generate_image(prompt: str, destination: Path, *, client=None) -> Path:
    """Generate one image for `prompt` and save it to `destination`.

    Writes through a temporary file and renames on success, so a failure can
    never leave a truncated PNG behind for the validation step to find.
    """
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.images.generate(
        model=config.IMAGE_MODEL,
        prompt=prompt,
        size=config.IMAGE_SIZE,
        n=1,
        quality=config.IMAGE_QUALITY,
    )

    if not response.data or not response.data[0] or not response.data[0].b64_json:
        raise ValueError(f"No image data returned from API for prompt: {prompt!r}")

    image_bytes = base64.b64decode(response.data[0].b64_json)

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(image_bytes)
    os.replace(temporary, destination)

    return destination
```

- [x] **Step 4: Rewrite `scripts/ai/generate_images/generate_images.py`**

```python
"""Fan every item's image prompts out into independent, parallelizable jobs."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path

from .utils import generate_image


def image_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """Build one labelled, not-yet-run job per (item, prompt) pair.

    Returning callables rather than running them lets the pipeline merge these
    with the audio jobs into a single concurrency-capped pool.
    """
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number, prompt in enumerate(item.image_prompts, start=1):
            destination = image_path(item_number, prompt_number)
            label = f"image item {item_number} prompt {prompt_number}"
            jobs.append(
                (
                    label,
                    lambda p=prompt, d=destination: generate_image(p, d, client=client),
                )
            )
    return jobs


def generate_images(items: Sequence[Item], *, client=None) -> list[TaskResult]:
    """Generate every image in parallel. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, image_jobs(items, client=client))
```

- [x] **Step 5: Create `scripts/ai/generate_images/__init__.py`**

Create it as an empty file.

- [x] **Step 6: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_generate_images.py -v`
Expected: PASS, 12 passed

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "perf: generate images in parallel and drop fixed sleep delays"
```

---

### Task 7: Parallel audio generation on a TTS model that honours instructions

`generate_audio_for_item` passes `instructions=` while requesting `model="tts-1"`, which does not support that parameter — the carefully written voice direction has never had any effect. `gpt-4o-mini-tts` does support it.

**Files:**
- Modify: `scripts/ai/generate_audios/generate_audio.py`, `scripts/ai/generate_audios/utils.py`
- Create: `tests/test_generate_audio.py`

**Interfaces:**
- Consumes: `config.TTS_MODEL/TTS_VOICE/TTS_INSTRUCTIONS`; `models.Item`; `utils.paths.audio_path`; `utils.openai_support.with_retry`, `run_all`, `Job`
- Produces: `generate_audio_for_item(item: Item, destination: Path, *, client=None) -> Path` in `utils.py`; `audio_jobs(items, *, client=None) -> list[Job]` and `generate_audio_for_items(items, *, client=None) -> list[TaskResult]` in `generate_audio.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_generate_audio.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Item
from scripts.ai.generate_audios.generate_audio import audio_jobs, generate_audio_for_items
from scripts.ai.generate_audios.utils import generate_audio_for_item

MP3_BYTES = b"ID3\x03\x00\x00\x00fake mp3 payload"


class FakeSpeech:
    def __init__(self, payload=MP3_BYTES, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(iter_bytes=lambda: iter([self.payload]))


def fake_client(payload=MP3_BYTES, error=None):
    speech = FakeSpeech(payload=payload, error=error)
    return SimpleNamespace(audio=SimpleNamespace(speech=speech)), speech


def two_items():
    return [
        Item("Dodo", "A flightless bird.", ("a", "b", "c")),
        Item("Moa", "A very tall bird.", ("a", "b", "c")),
    ]


def test_writes_the_audio_bytes(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "item_01.mp3"
    assert generate_audio_for_item(two_items()[0], destination, client=client) == destination
    assert destination.read_bytes() == MP3_BYTES


def test_narrates_title_then_description(tmp_path):
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert speech.calls[0]["input"] == "Dodo. A flightless bird."


def test_uses_the_configured_tts_model_and_voice(tmp_path, monkeypatch):
    monkeypatch.setattr("config.TTS_MODEL", "test-tts")
    monkeypatch.setattr("config.TTS_VOICE", "coral")
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert speech.calls[0]["model"] == "test-tts"
    assert speech.calls[0]["voice"] == "coral"


def test_sends_the_voice_instructions(tmp_path):
    # The old code sent these to tts-1, which silently ignored them.
    client, speech = fake_client()
    generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)
    assert "conversational" in speech.calls[0]["instructions"]


def test_creates_parent_directories(tmp_path):
    client, _ = fake_client()
    destination = tmp_path / "deep" / "a.mp3"
    generate_audio_for_item(two_items()[0], destination, client=client)
    assert destination.exists()


def test_rejects_an_empty_response(tmp_path):
    client, _ = fake_client(payload=b"")
    with pytest.raises(ValueError, match="No audio data"):
        generate_audio_for_item(two_items()[0], tmp_path / "a.mp3", client=client)


def test_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(payload=b"")
    destination = tmp_path / "a.mp3"
    with pytest.raises(ValueError):
        generate_audio_for_item(two_items()[0], destination, client=client)
    assert not destination.exists()


def test_audio_jobs_fans_out_one_job_per_item():
    client, _ = fake_client()
    jobs = audio_jobs(two_items(), client=client)
    assert len(jobs) == 2
    assert [label for label, _ in jobs] == ["audio item 1", "audio item 2"]


def test_audio_jobs_are_not_executed_when_built():
    client, speech = fake_client()
    audio_jobs(two_items(), client=client)
    assert speech.calls == []


def test_generate_audio_for_items_writes_every_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client()
    results = generate_audio_for_items(two_items(), client=client)
    assert all(r.ok for r in results)
    assert Path("outputs/audio_output/item_01.mp3").exists()
    assert Path("outputs/audio_output/item_02.mp3").exists()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_generate_audio.py -v`
Expected: FAIL — `ImportError: cannot import name 'audio_jobs'`

- [x] **Step 3: Rewrite `scripts/ai/generate_audios/utils.py`**

```python
"""Single-item narration against the OpenAI speech API."""

import os
from pathlib import Path

import config
from models import Item
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry


@with_retry
def generate_audio_for_item(item: Item, destination: Path, *, client=None) -> Path:
    """Narrate one item's title and description into `destination`."""
    client = client or get_open_ai_client()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = client.audio.speech.create(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        instructions=config.TTS_INSTRUCTIONS,
        input=item.narration,
    )

    payload = b"".join(response.iter_bytes())
    if not payload:
        raise ValueError(f"No audio data returned from API for item: {item.title!r}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)

    return destination
```

- [x] **Step 4: Rewrite `scripts/ai/generate_audios/generate_audio.py`**

```python
"""Fan item narration out into independent, parallelizable jobs."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import audio_path

from .utils import generate_audio_for_item


def audio_jobs(items: Sequence[Item], *, client=None) -> list[Job]:
    """Build one labelled, not-yet-run narration job per item."""
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        destination = audio_path(item_number)
        jobs.append(
            (
                f"audio item {item_number}",
                lambda i=item, d=destination: generate_audio_for_item(
                    i, d, client=client
                ),
            )
        )
    return jobs


def generate_audio_for_items(
    items: Sequence[Item], *, client=None
) -> list[TaskResult]:
    """Narrate every item in parallel. Convenience wrapper for standalone use."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, audio_jobs(items, client=client))
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_generate_audio.py -v`
Expected: PASS, 11 passed

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "fix: use gpt-4o-mini-tts so voice instructions apply; parallelize narration"
```

---

### Task 8: Titled images — fix the geometry bug, the font fallback, and the blur cost

Three concrete defects here. `new_height = int(1080 * aspect_ratio)` multiplies where it should divide — invisible today only because every generated image is square. The font list (`arial.ttf`, `Arial-Bold.ttf`, …) resolves on macOS and Windows but on Linux silently falls through to `ImageFont.load_default()`, which renders titles at roughly 10px. And `GaussianBlur(radius=90)` on a full 1080×1920 image runs once per titled image — fifteen times per video — when the same visual result is available for a fraction of the cost.

**Files:**
- Modify: `scripts/non_ai/create_titled_images_short/utils.py`, `scripts/non_ai/create_titled_images_short/create_titled_images_short.py`
- Create: `scripts/non_ai/__init__.py`, `scripts/non_ai/create_titled_images_short/__init__.py`, `tests/test_titled_images.py`

**Interfaces:**
- Consumes: `config.VIDEO_WIDTH/VIDEO_HEIGHT/TITLE_*/BACKGROUND_*`; `models.Item`; `utils.paths.image_path`, `titled_image_path`
- Produces: in `utils.py` — `TitleFontNotFoundError`, `scaled_height(src_w, src_h, target_w) -> int`, `wrap_text(text, font, max_width) -> list[str]`, `load_title_font(size) -> ImageFont.FreeTypeFont`, `blurred_background(source, size) -> Image.Image`, `create_titled_image_short(source, title, destination) -> Path`. In `create_titled_images_short.py` — `create_titled_images_for_items_short(items) -> list[TaskResult]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_titled_images.py`:

```python
from pathlib import Path

import pytest
from PIL import Image, ImageFont

import config
from models import Item
from scripts.non_ai.create_titled_images_short.create_titled_images_short import (
    create_titled_images_for_items_short,
)
from scripts.non_ai.create_titled_images_short.utils import (
    blurred_background,
    create_titled_image_short,
    load_title_font,
    scaled_height,
    wrap_text,
)


@pytest.fixture
def square_image(tmp_path):
    path = tmp_path / "src.png"
    Image.new("RGB", (1024, 1024), (30, 90, 150)).save(path)
    return path


@pytest.fixture
def wide_image(tmp_path):
    path = tmp_path / "wide.png"
    Image.new("RGB", (1600, 900), (30, 90, 150)).save(path)
    return path


def test_scaled_height_preserves_a_square():
    assert scaled_height(1024, 1024, 1080) == 1080


def test_scaled_height_preserves_a_landscape_ratio():
    # The old code multiplied by the aspect ratio, producing 1920 here.
    assert scaled_height(1600, 900, 1080) == 608


def test_scaled_height_preserves_a_portrait_ratio():
    assert scaled_height(900, 1600, 1080) == 1920


def test_scaled_height_rejects_zero_height():
    with pytest.raises(ValueError):
        scaled_height(1024, 0, 1080)


def test_load_title_font_returns_a_real_truetype_font():
    font = load_title_font(120)
    assert isinstance(font, ImageFont.FreeTypeFont)
    # A silent fallback to load_default() would give a ~10px bitmap font.
    assert font.getbbox("Hg")[3] > 50


def test_load_title_font_is_cached():
    assert load_title_font(120) is load_title_font(120)


def test_wrap_text_keeps_short_text_on_one_line():
    font = load_title_font(120)
    assert wrap_text("Dodo", font, 980) == ["Dodo"]


def test_wrap_text_splits_long_text():
    font = load_title_font(120)
    lines = wrap_text("The Extraordinarily Long Extinct Bird Name", font, 980)
    assert len(lines) > 1
    assert " ".join(lines) == "The Extraordinarily Long Extinct Bird Name"


def test_wrap_text_emits_an_oversized_word_on_its_own_line():
    font = load_title_font(120)
    lines = wrap_text("Supercalifragilisticexpialidocious", font, 200)
    assert lines == ["Supercalifragilisticexpialidocious"]


def test_wrap_text_handles_empty_input():
    font = load_title_font(120)
    assert wrap_text("", font, 980) == []


def test_blurred_background_returns_the_requested_size(square_image):
    source = Image.open(square_image)
    result = blurred_background(source, (1080, 1920))
    assert result.size == (1080, 1920)
    assert result.mode == "RGB"


def test_blurred_background_actually_blurs(square_image):
    source = Image.new("RGB", (200, 200))
    for x in range(200):
        for y in range(200):
            source.putpixel((x, y), (255, 0, 0) if (x // 10) % 2 else (0, 0, 255))
    result = blurred_background(source, (100, 100))
    # Hard red/blue stripes must average into intermediate colours.
    colours = {result.getpixel((x, 50)) for x in range(10, 90)}
    assert not colours <= {(255, 0, 0), (0, 0, 255)}


def test_create_titled_image_writes_correct_dimensions(square_image, tmp_path):
    destination = tmp_path / "out.png"
    create_titled_image_short(square_image, "Dodo", destination)
    with Image.open(destination) as result:
        assert result.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_create_titled_image_handles_a_non_square_source(wide_image, tmp_path):
    # The aspect-ratio bug made this produce a 1080x1920 foreground that
    # completely covered the background.
    destination = tmp_path / "out.png"
    create_titled_image_short(wide_image, "Wide", destination)
    with Image.open(destination) as result:
        assert result.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)


def test_create_titled_image_creates_parent_directories(square_image, tmp_path):
    destination = tmp_path / "deep" / "out.png"
    create_titled_image_short(square_image, "Dodo", destination)
    assert destination.exists()


def test_create_titled_image_raises_on_a_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_titled_image_short(tmp_path / "nope.png", "X", tmp_path / "out.png")


def test_batch_renders_every_item_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("outputs/image_output").mkdir(parents=True)
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in range(1, 4):
        Image.new("RGB", (1024, 1024), (10, 20, 30)).save(
            Path(f"outputs/image_output/item_01_prompt_{prompt_number:02d}.png")
        )

    results = create_titled_images_for_items_short(items)

    assert all(r.ok for r in results)
    assert Path("outputs/titled_image_output/item_01_prompt_01_short.png").exists()
    assert Path("outputs/titled_image_output/item_01_prompt_03_short.png").exists()


def test_batch_reports_a_missing_source_without_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("outputs/image_output").mkdir(parents=True)
    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    Image.new("RGB", (1024, 1024)).save(
        Path("outputs/image_output/item_01_prompt_01.png")
    )

    results = create_titled_images_for_items_short(items)

    assert sum(1 for r in results if r.ok) == 1
    assert sum(1 for r in results if not r.ok) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_titled_images.py -v`
Expected: FAIL — `ImportError: cannot import name 'scaled_height'`

- [ ] **Step 3: Rewrite `scripts/non_ai/create_titled_images_short/utils.py`**

```python
"""Compose a source image and its title into a 1080x1920 Shorts frame."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config


class TitleFontNotFoundError(RuntimeError):
    """No usable TrueType font was found on this machine."""


# Absolute paths first (reliable), then bare names for PIL's own font search.
# Falling back to ImageFont.load_default() is deliberately NOT an option: it
# silently renders titles at ~10px, which is how this broke on Linux.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "Arial Bold.ttf",
    "Arial.ttf",
    "arial.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
)


@lru_cache(maxsize=8)
def load_title_font(size: int) -> ImageFont.FreeTypeFont:
    """Find a usable TrueType font, or fail loudly.

    Cached, because this used to be re-resolved once per titled image.
    """
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    raise TitleFontNotFoundError(
        "No usable TrueType font found. Tried:\n  "
        + "\n  ".join(FONT_CANDIDATES)
        + "\nInstall one (on Debian/Ubuntu: apt install fonts-dejavu-core) or add "
        "a path to FONT_CANDIDATES."
    )


def scaled_height(source_width: int, source_height: int, target_width: int) -> int:
    """Height that preserves the aspect ratio when scaling to `target_width`."""
    if source_height <= 0 or source_width <= 0:
        raise ValueError(
            f"Source image has a non-positive dimension: "
            f"{source_width}x{source_height}"
        )
    return round(target_width * source_height / source_width)


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """Greedily wrap `text` to lines no wider than `max_width` pixels."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        elif current:
            lines.append(" ".join(current))
            current = [word]
        else:
            # A single word wider than the line; emit it and move on.
            lines.append(word)
            current = []

    if current:
        lines.append(" ".join(current))
    return lines


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

    overlay = Image.new(
        "RGBA", size, (255, 255, 255, config.BACKGROUND_OVERLAY_ALPHA)
    )
    return Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")


def create_titled_image_short(
    source_path: Path, title: str, destination: Path
) -> Path:
    """Render `source_path` onto a blurred backdrop with `title` beneath it."""
    source_path = Path(source_path)
    destination = Path(destination)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)

    canvas_size = (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)

    # Opened once and reused for both foreground and background; the previous
    # version opened the same file twice.
    with Image.open(source_path) as opened:
        source = opened.convert("RGB")

        foreground_height = scaled_height(
            source.width, source.height, config.VIDEO_WIDTH
        )
        foreground = source.resize(
            (config.VIDEO_WIDTH, foreground_height), Image.Resampling.LANCZOS
        )
        canvas = blurred_background(source, canvas_size)

    foreground_top = (config.VIDEO_HEIGHT - foreground_height - 80) // 2
    canvas.paste(foreground, (0, foreground_top))

    font = load_title_font(config.TITLE_FONT_SIZE)
    max_text_width = config.VIDEO_WIDTH - (2 * config.TITLE_SIDE_MARGIN)
    lines = wrap_text(title, font, max_text_width)

    if lines:
        draw = ImageDraw.Draw(canvas)
        line_height = config.TITLE_FONT_SIZE + config.TITLE_LINE_SPACING
        block_height = len(lines) * line_height
        block_top = (
            foreground_top + foreground_height + config.TITLE_GAP_BELOW_IMAGE
        )
        for index, line in enumerate(lines):
            y = block_top + (index * line_height) - (block_height // 2)
            draw.text(
                (config.VIDEO_WIDTH // 2, y),
                line,
                fill=config.TITLE_COLOR,
                font=font,
                anchor="mm",
            )

    canvas.save(destination)
    return destination
```

- [ ] **Step 4: Rewrite `scripts/non_ai/create_titled_images_short/create_titled_images_short.py`**

Compositing is CPU-bound but Pillow releases the GIL inside its C routines, so a thread pool genuinely helps here.

```python
"""Render a titled Shorts frame for every generated image."""

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import config
from models import Item
from utils.openai_support import Job, TaskResult, run_all
from utils.paths import image_path, titled_image_path

from .utils import create_titled_image_short


def titled_image_jobs(items: Sequence[Item]) -> list[Job]:
    jobs: list[Job] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number in range(1, len(item.image_prompts) + 1):
            source = image_path(item_number, prompt_number)
            destination = titled_image_path(item_number, prompt_number)
            label = f"titled image item {item_number} prompt {prompt_number}"
            jobs.append(
                (
                    label,
                    lambda s=source, t=item.title, d=destination: (
                        create_titled_image_short(s, t, d)
                    ),
                )
            )
    return jobs


def create_titled_images_for_items_short(
    items: Sequence[Item],
) -> list[TaskResult]:
    """Render every titled image. Pillow releases the GIL, so threads help."""
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        return run_all(executor, titled_image_jobs(items))
```

- [ ] **Step 5: Create the `__init__.py` files**

Create `scripts/non_ai/__init__.py` and `scripts/non_ai/create_titled_images_short/__init__.py` as empty files.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_titled_images.py -v`
Expected: PASS, 18 passed

- [ ] **Step 7: Measure the blur speedup**

```bash
./venv/bin/python -c "
import time
from PIL import Image, ImageFilter
import config
from scripts.non_ai.create_titled_images_short.utils import blurred_background

src = Image.new('RGB', (1024, 1024), (40, 80, 160))
size = (1080, 1920)

start = time.perf_counter()
for _ in range(5):
    old = src.resize(size, Image.Resampling.LANCZOS).filter(
        ImageFilter.GaussianBlur(radius=config.BACKGROUND_BLUR_RADIUS))
print(f'old full-res blur: {(time.perf_counter()-start)/5*1000:.1f} ms/image')

start = time.perf_counter()
for _ in range(5):
    new = blurred_background(src, size)
print(f'new downscaled blur: {(time.perf_counter()-start)/5*1000:.1f} ms/image')
"
```

Expected: the new path is at least 10x faster. Record both numbers in the commit message.

- [ ] **Step 8: Eyeball one rendered frame**

Automated tests confirm geometry but not that it looks right. Render one and open it.

```bash
./venv/bin/python -c "
from pathlib import Path
from scripts.non_ai.create_titled_images_short.utils import create_titled_image_short
src = sorted(Path('generated_data').glob('*/images/item_01_prompt_01.png'))[0]
out = Path('/tmp/titled_preview.png')
create_titled_image_short(src, 'Woolly Mammoth', out)
print(out)
"
open /tmp/titled_preview.png
```

Expected: 1080×1920, source image centred on a soft blurred backdrop, title in large black text below it. If the title is tiny, `load_title_font` picked the wrong font — fix it rather than accepting it.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "fix: correct titled-image aspect ratio and font fallback; speed up blur"
```

---

### Task 9: Video assembly — fix the audio handling, unhardcode the image count, speed up the zoom

Per item, the mp3 is currently opened **four separate times**: once in `generate_video_short` to read its duration, then three more times inside `create_audio_with_delays` (the real clip plus two `volumex(0)` copies used as silence). `create_item_video_clip` hardcodes `range(1, 4)`, so anything other than exactly three images breaks. And the zoom does a full-frame LANCZOS resize on every frame at 24fps — the single most expensive operation in the render.

**Files:**
- Modify: `scripts/non_ai/generate_video_short/generate_video_short.py`, `scripts/non_ai/generate_video_short/utils.py`
- Create: `scripts/non_ai/generate_video_short/__init__.py`, `tests/test_video.py`

**Interfaces:**
- Consumes: `config.VIDEO_*/INTRO_SILENCE_SECONDS/OUTRO_SILENCE_SECONDS/ZOOM_END_SCALE`; `models.Item`; `utils.paths.audio_path`, `titled_image_path`, `video_output_path`, `VIDEO_OUTPUT_DIR`
- Produces: in `utils.py` — `zoom_scale(t, segment_duration, end_scale) -> float`, `segment_bounds(total_duration, count) -> list[tuple[float, float]]`, `build_image_clip(path, segment_duration, start_time)`, `build_item_audio(audio_path) -> tuple[clip, float]`, `build_item_clip(item_number, image_count) -> clip`. In `generate_video_short.py` — `generate_video_short(items: Sequence[Item]) -> Path`

- [ ] **Step 1: Write the failing tests**

The pure timing/scaling maths is tested directly; the moviepy assembly is covered by one slow end-to-end render marked so it can be deselected.

Create `tests/test_video.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

import config
from models import Item
from scripts.non_ai.generate_video_short.utils import segment_bounds, zoom_scale


def test_zoom_starts_at_one():
    assert zoom_scale(0.0, 3.0, 1.2) == pytest.approx(1.0)


def test_zoom_reaches_the_end_scale():
    assert zoom_scale(3.0, 3.0, 1.2) == pytest.approx(1.2)


def test_zoom_is_linear_at_the_midpoint():
    assert zoom_scale(1.5, 3.0, 1.2) == pytest.approx(1.1)


def test_zoom_clamps_past_the_end():
    # moviepy can request t marginally beyond the clip duration.
    assert zoom_scale(3.5, 3.0, 1.2) == pytest.approx(1.2)


def test_zoom_clamps_before_the_start():
    assert zoom_scale(-1.0, 3.0, 1.2) == pytest.approx(1.0)


def test_zoom_handles_zero_duration():
    assert zoom_scale(0.0, 0.0, 1.2) == pytest.approx(1.0)


def test_segment_bounds_splits_evenly():
    bounds = segment_bounds(9.0, 3)
    assert bounds == [(0.0, 3.0), (3.0, 3.0), (6.0, 3.0)]


def test_segment_bounds_covers_the_whole_duration():
    bounds = segment_bounds(10.0, 3)
    start, duration = bounds[-1]
    assert start + duration == pytest.approx(10.0)


def test_segment_bounds_handles_a_single_image():
    assert segment_bounds(5.0, 1) == [(0.0, 5.0)]


def test_segment_bounds_handles_four_images():
    # The old code hardcoded range(1, 4) and could not do this.
    assert len(segment_bounds(8.0, 4)) == 4


def test_segment_bounds_rejects_zero_images():
    with pytest.raises(ValueError):
        segment_bounds(5.0, 0)


@pytest.mark.slow
def test_renders_a_real_video(tmp_path, monkeypatch):
    """End-to-end render with tiny assets. Deselect with -m 'not slow'."""
    from scripts.ai.generate_audios.utils import generate_audio_for_item  # noqa: F401
    from scripts.non_ai.generate_video_short.generate_video_short import (
        generate_video_short,
    )
    from utils.paths import audio_path, ensure_output_dirs, titled_image_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "VIDEO_WIDTH", 108)
    monkeypatch.setattr(config, "VIDEO_HEIGHT", 192)
    monkeypatch.setattr(config, "VIDEO_FPS", 6)
    ensure_output_dirs()

    items = [Item("Dodo", "A bird.", ("a", "b", "c"))]
    for prompt_number in range(1, 4):
        Image.new("RGB", (108, 192), (20, 40, 60)).save(
            titled_image_path(1, prompt_number)
        )

    # A one-second silent mp3 generated with ffmpeg (bundled with imageio-ffmpeg).
    import subprocess

    import imageio_ffmpeg

    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
            str(audio_path(1)),
        ],
        check=True,
        capture_output=True,
    )

    output = generate_video_short(items)
    assert output.exists()
    assert output.stat().st_size > 0
```

Register the `slow` marker by appending to `pytest.ini`:

```ini
markers =
    slow: end-to-end renders that take several seconds
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_video.py -v -m "not slow"`
Expected: FAIL — `ImportError: cannot import name 'segment_bounds'`

- [ ] **Step 3: Rewrite `scripts/non_ai/generate_video_short/utils.py`**

The zoom now builds a `VideoClip` with a closure over an already-decoded PIL image, rather than an `ImageClip` wrapped in `.fl()`. That removes a numpy round-trip per frame, and BILINEAR replaces LANCZOS — on a continuously scaling still at 24fps the difference is not visible, and it is several times cheaper.

```python
"""Assemble titled images and narration into per-item video clips."""

from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoClip,
)
from PIL import Image

import config
from utils.paths import audio_path, titled_image_path


def zoom_scale(t: float, segment_duration: float, end_scale: float) -> float:
    """Linear zoom from 1.0 to `end_scale`, clamped at both ends.

    Clamping matters: moviepy sometimes samples marginally outside [0, duration].
    """
    if segment_duration <= 0:
        return 1.0
    progress = min(max(t / segment_duration, 0.0), 1.0)
    return 1.0 + (end_scale - 1.0) * progress


def segment_bounds(total_duration: float, count: int) -> list[tuple[float, float]]:
    """Split `total_duration` into `count` (start, duration) pairs."""
    if count < 1:
        raise ValueError(f"Need at least one image per item, got {count}")
    segment = total_duration / count
    return [(index * segment, segment) for index in range(count)]


def build_background_clip(duration: float) -> ColorClip:
    return ColorClip(
        size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(255, 255, 255)
    ).set_duration(duration)


def build_image_clip(image_path: Path, segment_duration: float, start_time: float):
    """A still image that slowly zooms in over `segment_duration`.

    The source is decoded once and captured in the closure, so each frame costs
    exactly one BILINEAR resize instead of a decode plus a LANCZOS resize.
    """
    with Image.open(image_path) as opened:
        source = opened.convert("RGB")
    base_width, base_height = source.size

    def make_frame(t):
        scale = zoom_scale(t, segment_duration, config.ZOOM_END_SCALE)
        resized = source.resize(
            (round(base_width * scale), round(base_height * scale)),
            Image.Resampling.BILINEAR,
        )
        return np.asarray(resized)

    clip = VideoClip(make_frame, duration=segment_duration)
    return clip.set_position("center").set_start(start_time)


def build_item_audio(item_number: int) -> tuple[CompositeAudioClip, float]:
    """Narration padded with leading and trailing silence.

    Returns the clip and its total duration, so callers do not need to reopen
    the file just to measure it. The previous implementation opened the same
    mp3 four times per item.
    """
    voice = AudioFileClip(str(audio_path(item_number)))
    total_duration = (
        config.INTRO_SILENCE_SECONDS + voice.duration + config.OUTRO_SILENCE_SECONDS
    )
    padded = CompositeAudioClip(
        [voice.set_start(config.INTRO_SILENCE_SECONDS)]
    ).set_duration(total_duration)
    return padded, total_duration


def build_item_clip(item_number: int, image_count: int):
    """One item: its images in sequence, over its narration."""
    audio, total_duration = build_item_audio(item_number)

    layers = [build_background_clip(total_duration)]
    for prompt_number, (start, duration) in enumerate(
        segment_bounds(total_duration, image_count), start=1
    ):
        layers.append(
            build_image_clip(
                titled_image_path(item_number, prompt_number), duration, start
            )
        )

    return CompositeVideoClip(layers).set_duration(total_duration).set_audio(audio)
```

- [ ] **Step 4: Rewrite `scripts/non_ai/generate_video_short/generate_video_short.py`**

```python
"""Concatenate per-item clips into the final vertical video."""

import os
from pathlib import Path
from typing import Sequence

from moviepy.editor import concatenate_videoclips

import config
from models import Item
from utils.paths import VIDEO_OUTPUT_DIR, video_output_path

from .utils import build_item_clip


def generate_video_short(items: Sequence[Item]) -> Path:
    """Render a 1080x1920 video from the titled images and narration on disk.

    Each item shows its images in sequence over its narration, with a short
    silence before and after, and a slow zoom on every image.
    """
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = video_output_path()

    clips = [
        build_item_clip(item_number, len(item.image_prompts))
        for item_number, item in enumerate(items, start=1)
    ]

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

    return output_path
```

- [ ] **Step 5: Create `scripts/non_ai/generate_video_short/__init__.py`**

Create it as an empty file.

- [ ] **Step 6: Run the fast tests to verify they pass**

Run: `./venv/bin/pytest tests/test_video.py -v -m "not slow"`
Expected: PASS, 11 passed

- [ ] **Step 7: Run the slow end-to-end render test**

Run: `./venv/bin/pytest tests/test_video.py -v -m slow`
Expected: PASS, 1 passed. This takes 10-30 seconds and shells out to ffmpeg.

- [ ] **Step 8: Render a real video from existing assets and compare against the old one**

`outputs/video_output/final_video_short.mp4` is the video the old code produced. Move it aside, render fresh, and compare.

```bash
cp outputs/video_output/final_video_short.mp4 /tmp/video_before.mp4
time ./venv/bin/python -c "
from models import load_items
from scripts.non_ai.generate_video_short.generate_video_short import generate_video_short
from utils.paths import list_items_path
print(generate_video_short(load_items(list_items_path())))
"
open /tmp/video_before.mp4 outputs/video_output/final_video_short.mp4
```

Expected: the new render is faster, and visually the two are equivalent — same duration, same zoom, audio in sync, silence before and after each item. Record the timing in the commit message. If the new video looks different in any way other than being sharper or faster, stop and investigate.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "perf: cheaper zoom and single audio handle per item; support any image count"
```

---

### Task 10: Archiving — run it last, include the video, fix the slug

`save_to_generated_data` is currently called from `main.py` *before* titled images and the video exist, so the archived folder never contains the finished video — the whole point of archiving. It also hardcodes `outputs/audio_output` rather than using the path helpers.

**Files:**
- Modify: `scripts/non_ai/save_to_generated_data/save_to_generated_data.py`
- Create: `scripts/non_ai/save_to_generated_data/__init__.py`, `tests/test_archive.py`

**Interfaces:**
- Consumes: `models.Item`, `models.save_items`; `utils.paths.*`
- Produces: `save_to_generated_data(topic: str, items: Sequence[Item]) -> Path`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archive.py`:

```python
from pathlib import Path

import pytest

from models import Item, load_items
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_to_generated_data,
)
from utils.paths import ensure_output_dirs


@pytest.fixture
def populated_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    Path("outputs/audio_output/item_01.mp3").write_bytes(b"audio")
    Path("outputs/image_output/item_01_prompt_01.png").write_bytes(b"image")
    Path("outputs/titled_image_output/item_01_prompt_01_short.png").write_bytes(b"tit")
    Path("outputs/video_output/final_video_short.mp4").write_bytes(b"video")
    return tmp_path


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def test_creates_a_slugged_folder(populated_outputs):
    folder = save_to_generated_data("Top 5: Extinct Animals!", one_item())
    assert folder == Path("generated_data/top_5_extinct_animals")
    assert folder.is_dir()


def test_archives_the_item_list(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert load_items(folder / "list_items.json") == one_item()


def test_archives_audio(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "audio" / "item_01.mp3").read_bytes() == b"audio"


def test_archives_images(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "images" / "item_01_prompt_01.png").read_bytes() == b"image"


def test_archives_titled_images(populated_outputs):
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "titled_images" / "item_01_prompt_01_short.png").exists()


def test_archives_the_final_video(populated_outputs):
    # The old pipeline ran this before the video existed, so it never got saved.
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "final_video_short.mp4").read_bytes() == b"video"


def test_tolerates_a_missing_video(populated_outputs):
    Path("outputs/video_output/final_video_short.mp4").unlink()
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert folder.is_dir()
    assert not (folder / "final_video_short.mp4").exists()


def test_is_idempotent(populated_outputs):
    save_to_generated_data("Extinct Animals", one_item())
    folder = save_to_generated_data("Extinct Animals", one_item())
    assert (folder / "audio" / "item_01.mp3").exists()


def test_falls_back_to_a_timestamp_for_an_unusable_topic(populated_outputs):
    folder = save_to_generated_data("!!!", one_item())
    assert folder.parent == Path("generated_data")
    assert folder.is_dir()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_archive.py -v`
Expected: FAIL — `TypeError` on the changed signature

- [ ] **Step 3: Rewrite `scripts/non_ai/save_to_generated_data/save_to_generated_data.py`**

```python
"""Archive one finished run into `generated_data/<topic-slug>/`."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence

from models import Item, save_items
from utils.paths import (
    ARCHIVED_LIST_FILENAME,
    AUDIO_OUTPUT_DIR,
    GENERATED_DATA_ROOT,
    IMAGE_OUTPUT_DIR,
    TITLED_IMAGE_OUTPUT_DIR,
    VIDEO_FILENAME,
    slugify,
    video_output_path,
)


def _copy_tree(source: Path, destination: Path, suffix: str) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    if not source.is_dir():
        return copied
    for entry in sorted(source.iterdir()):
        if entry.is_file() and entry.suffix == suffix:
            shutil.copy2(entry, destination / entry.name)
            copied += 1
    return copied


def save_to_generated_data(topic: str, items: Sequence[Item]) -> Path:
    """Copy this run's list, audio, images, titled images and video into an archive.

    Must run *after* the video is rendered — the previous pipeline called this
    before video assembly, so the archive never contained the finished video.
    """
    slug = slugify(topic)
    if slug == "untitled":
        slug = datetime.now().strftime("%Y%m%d_%H%M%S")

    folder = GENERATED_DATA_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)

    save_items(items, folder / ARCHIVED_LIST_FILENAME)

    audio_count = _copy_tree(AUDIO_OUTPUT_DIR, folder / "audio", ".mp3")
    image_count = _copy_tree(IMAGE_OUTPUT_DIR, folder / "images", ".png")
    titled_count = _copy_tree(
        TITLED_IMAGE_OUTPUT_DIR, folder / "titled_images", ".png"
    )

    video = video_output_path()
    if video.exists():
        shutil.copy2(video, folder / VIDEO_FILENAME)

    print(
        f"\nArchived to {folder}: {audio_count} audio, {image_count} images, "
        f"{titled_count} titled images"
        + (", 1 video" if video.exists() else ", no video")
    )
    return folder
```

- [ ] **Step 4: Create `scripts/non_ai/save_to_generated_data/__init__.py`**

Create it as an empty file.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_archive.py -v`
Expected: PASS, 9 passed

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix: archive after video render and include the video in the archive"
```

---

### Task 11: `pipeline.py` and the `main.py` CLI

This wires everything together and adds the missing safety net: today, if one image fails, the pipeline prints "Continuing with next item...", proceeds, and then crashes several minutes later inside moviepy with a `FileNotFoundError` for a titled image. Validation between stages turns that into an immediate, readable error.

**Files:**
- Create: `pipeline.py`, `tests/test_pipeline.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: everything built so far
- Produces: `PipelineError(RuntimeError)`, `missing_media(items) -> list[Path]`, `missing_titled_images(items) -> list[Path]`, `run_pipeline(topic: str, num_items: int, *, client=None) -> Path`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

from models import Item
from pipeline import PipelineError, missing_media, missing_titled_images
from utils.paths import audio_path, ensure_output_dirs, image_path, titled_image_path


def one_item():
    return [Item("Dodo", "A bird.", ("a", "b", "c"))]


def write_media(items, *, skip=()):
    for item_number, item in enumerate(items, start=1):
        if ("audio", item_number) not in skip:
            audio_path(item_number).write_bytes(b"audio")
        for prompt_number in range(1, len(item.image_prompts) + 1):
            if ("image", item_number, prompt_number) in skip:
                continue
            image_path(item_number, prompt_number).write_bytes(b"image")


def test_missing_media_is_empty_when_everything_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item())
    assert missing_media(one_item()) == []


def test_missing_media_reports_a_missing_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item(), skip=[("image", 1, 2)])
    assert missing_media(one_item()) == [image_path(1, 2)]


def test_missing_media_reports_a_missing_audio_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item(), skip=[("audio", 1)])
    assert missing_media(one_item()) == [audio_path(1)]


def test_missing_media_reports_an_empty_file(tmp_path, monkeypatch):
    # A zero-byte file would pass an exists() check but break the renderer.
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    write_media(one_item())
    image_path(1, 1).write_bytes(b"")
    assert image_path(1, 1) in missing_media(one_item())


def test_missing_titled_images_reports_gaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_output_dirs()
    titled_image_path(1, 1).write_bytes(b"x")
    missing = missing_titled_images(one_item())
    assert titled_image_path(1, 2) in missing
    assert titled_image_path(1, 1) not in missing


def test_pipeline_error_is_a_runtime_error():
    assert issubclass(PipelineError, RuntimeError)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: Write `pipeline.py`**

The key structural change: image jobs and audio jobs are submitted into *one* executor, so they interleave under a single global concurrency cap rather than running as two sequential stages.

```python
"""Stage orchestration for the video generation pipeline."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import config
from models import Item, save_items
from scripts.ai.generate_audios.generate_audio import audio_jobs
from scripts.ai.generate_images.generate_images import image_jobs
from scripts.ai.generate_list.generate_list import generate_list
from scripts.non_ai.create_titled_images_short.create_titled_images_short import (
    create_titled_images_for_items_short,
)
from scripts.non_ai.generate_video_short.generate_video_short import (
    generate_video_short,
)
from scripts.non_ai.save_to_generated_data.save_to_generated_data import (
    save_to_generated_data,
)
from utils.openai_support import describe_failures, run_all
from utils.paths import (
    audio_path,
    ensure_output_dirs,
    image_path,
    list_items_path,
    titled_image_path,
)


class PipelineError(RuntimeError):
    """A stage produced incomplete output, so the pipeline cannot continue."""


def _unusable(path: Path) -> bool:
    """A file is unusable if it is absent or empty."""
    return not path.exists() or path.stat().st_size == 0


def missing_media(items: Sequence[Item]) -> list[Path]:
    """Every expected image and audio file that is absent or empty."""
    missing: list[Path] = []
    for item_number, item in enumerate(items, start=1):
        candidate = audio_path(item_number)
        if _unusable(candidate):
            missing.append(candidate)
        for prompt_number in range(1, len(item.image_prompts) + 1):
            candidate = image_path(item_number, prompt_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def missing_titled_images(items: Sequence[Item]) -> list[Path]:
    """Every expected titled image that is absent or empty."""
    missing: list[Path] = []
    for item_number, item in enumerate(items, start=1):
        for prompt_number in range(1, len(item.image_prompts) + 1):
            candidate = titled_image_path(item_number, prompt_number)
            if _unusable(candidate):
                missing.append(candidate)
    return missing


def _fail(stage: str, paths: Sequence[Path]) -> None:
    listing = "\n".join(f"  - {path}" for path in paths)
    raise PipelineError(
        f"{stage} did not produce {len(paths)} required file(s):\n{listing}\n"
        f"Fix the underlying errors above and re-run."
    )


def run_pipeline(topic: str, num_items: int, *, client=None) -> Path:
    """Run every stage end to end and return the path to the finished video."""
    ensure_output_dirs()

    print(f"\n[1/5] Generating {num_items} items for '{topic}'...")
    items = generate_list(topic, num_items, client=client)
    save_items(items, list_items_path())
    for number, item in enumerate(items, start=1):
        print(f"  {number}. {item.title}")

    total_jobs = len(items) + sum(len(item.image_prompts) for item in items)
    print(
        f"\n[2/5] Generating {total_jobs} media assets "
        f"({config.MAX_CONCURRENT_REQUESTS} at a time)..."
    )
    # One shared pool, so image and audio work interleaves under a single cap.
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        jobs = image_jobs(items, client=client) + audio_jobs(items, client=client)
        results = run_all(executor, jobs)

    failures = describe_failures(results)
    if failures:
        print(f"\n{failures}")

    missing = missing_media(items)
    if missing:
        _fail("Media generation", missing)

    print("\n[3/5] Rendering titled images...")
    titled_results = create_titled_images_for_items_short(items)
    titled_failures = describe_failures(titled_results)
    if titled_failures:
        print(f"\n{titled_failures}")

    missing = missing_titled_images(items)
    if missing:
        _fail("Titled image rendering", missing)

    print("\n[4/5] Assembling video...")
    video = generate_video_short(items)

    print("\n[5/5] Archiving...")
    save_to_generated_data(topic, items)

    return video
```

- [ ] **Step 4: Rewrite `main.py`**

Running `python main.py` with no arguments behaves exactly as it does today: two interactive prompts. The flags are additive, and they make the pipeline scriptable.

```python
"""Command-line entry point for the auto YouTube generator."""

import argparse
import sys

from models import InvalidItemsError
from pipeline import PipelineError, run_pipeline


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a YouTube Shorts video from a topic."
    )
    parser.add_argument("--topic", help="Video topic. Prompted for if omitted.")
    parser.add_argument(
        "--items", type=int, help="Number of items. Prompted for if omitted."
    )
    return parser.parse_args(argv)


def prompt_for_topic() -> str:
    while True:
        topic = input("Enter a topic for your video: ").strip()
        if topic:
            return topic
        print("Please enter a topic.")


def prompt_for_item_count() -> int:
    while True:
        raw = input("Enter the number of items for your video: ").strip()
        try:
            count = int(raw)
        except ValueError:
            print(f"'{raw}' is not a whole number. Try again.")
            continue
        if count < 1:
            print("Please enter a number of at least 1.")
            continue
        return count


def main(argv=None) -> int:
    args = parse_args(argv)

    topic = args.topic.strip() if args.topic else prompt_for_topic()
    if args.items is not None:
        if args.items < 1:
            print(f"--items must be at least 1, got {args.items}", file=sys.stderr)
            return 2
        num_items = args.items
    else:
        num_items = prompt_for_item_count()

    try:
        video = run_pipeline(topic, num_items)
    except (PipelineError, InvalidItemsError) as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    print(f"\nDone: {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the pipeline tests to verify they pass**

Run: `./venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS, 6 passed

- [ ] **Step 6: Run the whole suite**

Run: `./venv/bin/pytest -v`
Expected: all tests pass. Confirm nothing was broken by the rewiring.

- [ ] **Step 7: Verify no stale imports survive anywhere**

```bash
grep -rn "output_dirs\|output_file_names\|helper_functions\|clean_json_input\|zaza\|auto_youtube_generator\|tts-1\|gpt-4\"" \
  --include="*.py" . --exclude-dir=venv
```

Expected: no output. Any hit is a leftover from the old structure — fix it.

- [ ] **Step 8: Verify the CLI argument handling without spending API credits**

```bash
./venv/bin/python main.py --help
./venv/bin/python main.py --topic "x" --items 0; echo "exit=$?"
```

Expected: help text renders; the second command prints `--items must be at least 1, got 0` and exits with `exit=2`.

- [ ] **Step 9: Run the real pipeline end to end**

This spends API credits. Use a small item count.

```bash
time ./venv/bin/python main.py --topic "Top 3 Deep Sea Creatures" --items 3
```

Expected: all five stages print in order, no errors, and a playable video at `outputs/video_output/final_video_short.mp4`. Compare the wall-clock time against the pre-refactor baseline — with the sleeps gone and four requests in flight, media generation should be several times faster.

- [ ] **Step 10: Confirm the archive is complete**

```bash
find generated_data/top_3_deep_sea_creatures -type f | sort
open generated_data/top_3_deep_sea_creatures/final_video_short.mp4
```

Expected: `list_items.json`, `final_video_short.mp4`, 3 files under `audio/`, 9 under `images/`, 9 under `titled_images/`. The video plays correctly.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: add pipeline orchestration with asset validation and CLI flags"
```

---

### Task 12: Documentation

The README currently documents five `run_*.py` scripts that do not exist in the repository, and does not mention any of the configuration or the test suite.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Confirm the scripts the README references really are absent**

```bash
ls run_generate_list.py run_generate_audio.py run_generate_images.py \
   run_create_titled_images_short.py run_save_to_generated_data.py 2>&1
```

Expected: five "No such file or directory" errors, confirming the section must be removed rather than fixed.

- [ ] **Step 2: Update the pipeline description**

In `README.md`, replace the "Pipeline steps" list with the current order, which now archives last:

```markdown
**Pipeline steps:**

1. Generate a validated list of items (titles, descriptions, image prompts) via
   JSON-schema structured outputs.
2. Generate every image and voiceover in parallel, capped at
   `MAX_CONCURRENT_REQUESTS` concurrent API calls.
3. Verify every expected asset exists before continuing.
4. Compose each image onto a blurred 1080x1920 backdrop with its title.
5. Assemble the titled images and narration into a vertical video with a slow
   zoom on each image.
6. Archive the run — list, audio, images, titled images and the finished video
   — into `generated_data/<topic-slug>/`.
```

- [ ] **Step 3: Replace the "Run Individual Steps" section**

Delete the entire list of nonexistent `run_*.py` scripts and replace with:

```markdown
### Run the Pipeline

Interactively:

```bash
python main.py
```

Or non-interactively:

```bash
python main.py --topic "Top 5 Extinct Animals" --items 5
```

Output lands in `outputs/`, and a complete copy of the run is archived to
`generated_data/<topic-slug>/`.
```

- [ ] **Step 4: Add a Configuration section**

Insert after the API key section:

```markdown
## Configuration

Every tunable lives in `config.py` and can be overridden with an environment
variable of the same name (see `.env.example`). The ones worth knowing:

| Variable | Default | What it does |
|---|---|---|
| `MAX_CONCURRENT_REQUESTS` | `4` | Parallel OpenAI calls. Lower it if you hit rate limits. |
| `MAX_RETRIES` | `5` | Attempts per call before giving up. Rate limits and 5xx are retried with exponential backoff; content-policy rejections are not. |
| `TEXT_MODEL` | `gpt-4.1-mini` | Generates the item list. Must support JSON schema structured outputs. |
| `TTS_MODEL` | `gpt-4o-mini-tts` | Narration. Must support the `instructions` parameter. |
| `TTS_VOICE` | `ash` | Narration voice. |
| `IMAGE_MODEL` | `gpt-image-1` | Image generation. |
| `IMAGE_QUALITY` | `medium` | `low` is cheaper and faster; `high` is slower and costs more. |
| `VIDEO_PRESET` | `medium` | x264 preset. `ultrafast` renders quicker at a larger file size. |
```

- [ ] **Step 5: Add a Development section**

Append to the end of the README:

```markdown
## Development

Run the test suite:

```bash
pytest
```

Tests never make network calls — every OpenAI interaction goes through an
injected fake client, so the suite passes with `OPENAI_API_KEY` unset.

One end-to-end video render is marked `slow` and takes ~30 seconds. Skip it
during quick iteration:

```bash
pytest -m "not slow"
```

Note that `moviepy` is pinned to `1.0.3` and requires `decorator==4.4.2`.
Upgrading either will break video assembly.
```

- [ ] **Step 6: Verify every command in the README actually works**

```bash
./venv/bin/pytest -m "not slow"
./venv/bin/python main.py --help
```

Expected: tests pass; help text matches what the README describes.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: document the current pipeline, configuration, and test suite"
```

---

## Summary of what this plan changes

**Bugs fixed**
| Bug | Where it was | Task |
|---|---|---|
| Aspect ratio multiplied instead of divided | `create_titled_images_short/utils.py:62` | 8 |
| Font fallback silently renders ~10px titles on Linux | `create_titled_images_short/utils.py:94-117` | 8 |
| `instructions` sent to `tts-1`, which ignores it | `generate_audios/utils.py:26-30` | 7 |
| `range(1, 4)` hardcodes exactly three images per item | `generate_video_short/utils.py:58` | 9 |
| Archiving runs before the video exists | `main.py:33` | 10 |
| Partial failures crash later inside moviepy | no validation existed | 11 |
| `python-dotenv` imported but never declared | `requirements.txt` | 1 |
| Slug produces doubled/trailing underscores | `save_to_generated_data.py:14-15` | 2 |
| Content-policy rejections retried 3× pointlessly | all four `@retry` decorators | 4 |

**Performance**
- ~100s of hardcoded `time.sleep` removed; all API calls run 4-wide (Task 6, 7, 11)
- Background blur at 1/10 scale — expect >10× on that operation (Task 8)
- Per-frame LANCZOS on a full frame replaced with a closure-captured BILINEAR resize (Task 9)
- mp3 opened once per item instead of four times (Task 9)
- Font resolved once instead of once per image (Task 8)
- `write_videofile` uses all cores (Task 9)

**Structure**
- 4 duplicate constant definitions → one `config.py`
- 2 path modules with several bypassing call sites → one `utils/paths.py`
- JSON strings re-parsed at every stage → one `parse_items` call, typed `Item` objects thereafter
- `clean_json_input` deleted; structured outputs make it unnecessary
- ~1,100 lines of dead code and stale bytecode removed
- 0 tests → ~110 tests, none touching the network
