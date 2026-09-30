# List-Pipeline Web UI and Production Image Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the list-format pipeline on `main` the web UI from `feat/sectioned-scripts`, keep cheap models as the default, and add a "Production models" option that switches image generation to `gpt-image-2` at `high` quality for one run.

**Architecture:** The feature branch built the web UI before it replaced the list format, so commit `9c3cea3` (a descendant of `main`) already is "list pipeline + web UI". This branch is rebased onto it, the frontend API client that `.gitignore` hid is restored, and the production option is added as a preset in `config.py` that the run worker lays under the per-run overrides.

**Tech Stack:** Python 3.10+, FastAPI, pydantic, pytest; Vite, React 19, TypeScript, vitest, Testing Library, shadcn/ui components.

**Spec:** `docs/superpowers/specs/2026-09-30-list-web-ui-design.md`

## Global Constraints

- Work on branch `feat/list-web-ui`. Never commit to `main`.
- The item format stays the list format: `Item(title, description, image_prompts)`. Nothing from the sectioned-script, story-beat or chained-image work is brought over.
- Defaults are unchanged: `TEXT_MODEL=gpt-4.1-mini`, `TTS_MODEL=gpt-4o-mini-tts`, `IMAGE_MODEL=gpt-image-1`, `IMAGE_SIZE=1024x1024`, `IMAGE_QUALITY=medium`.
- The production preset is exactly `{"IMAGE_MODEL": "gpt-image-2", "IMAGE_QUALITY": "high"}`. It must not contain `IMAGE_SIZE`: a portrait image pushes the item title off the 1920px frame.
- The preset is not read from the environment and has no CLI flag.
- Precedence: explicit per-run override > production preset > `config` default.
- `frontend/src/lib/types.ts` mirrors `api/schemas.py` field for field. Change both together.
- Tests never make network calls; every OpenAI interaction goes through a fake client.
- Run Python commands from the repo root with the venv active: `source venv/bin/activate`.
- End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A request that omits `production_models` (curl, an older client) must start a normal cheap run, not fail validation. — Task 2, `test_creating_a_run_defaults_to_cheap_models`.
2. `production_models: null` must be rejected with 422 rather than silently treated as either value. — Task 2, `test_creating_a_run_rejects_a_null_production_flag`.
3. A production run that fails mid-stage must leave `config` on the cheap defaults, so the next run is not silently expensive. — Task 2, `test_a_failed_production_run_restores_the_defaults`.
4. A production run paused for item review must still be on production models after approval. — Task 2, `test_a_reviewed_production_run_keeps_the_preset`.
5. If `GET /api/config` fails, the New Run form must still offer the checkbox and send the flag. — Task 3, `still offers production models when the config request fails`.

---

### Task 1: Bring the list-era web UI onto the branch and restore the API client

**Files:**
- Branch: rebase `feat/list-web-ui` onto `9c3cea3`
- Modify: `.gitignore` (the `lib/` and `lib64/` rules)
- Create: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `frontend/src/lib/utils.ts`

**Interfaces:**
- Consumes: commit `9c3cea3` (adds `api/`, `frontend/`, staged `pipeline.py`, `tests/api/`).
- Produces: `frontend/src/lib/types.ts` exporting `RunStatus`, `TERMINAL_STATUSES`, `STAGE_SEQUENCE`, `ItemPayload`, `AssetStatus`, `RunSummary`, `RunDetail`, `CreateRunRequest`, `ConfigField`, `ConfigPayload`, `ArchiveSummary`, `ArchiveItem`, `ArchiveDetail`; `frontend/src/lib/api.ts` exporting `ApiError`, `getConfig`, `listRuns`, `createRun`, `getRun`, `approveItems`, `cancelRun`, `listArchives`, `getArchive`; `frontend/src/lib/utils.ts` exporting `cn`.

- [ ] **Step 1: Rebase the branch onto the list-era web UI commit**

The branch currently holds only docs commits on top of `main`, and it has not been pushed, so a rebase is safe.

```bash
git rebase 9c3cea3
git log --oneline -4
```

Expected: the docs commits now sit on top of `9c3cea3 fix: serve index.html for client-side routes in the built frontend`. `ls api frontend/src/pages` lists files.

- [ ] **Step 2: Install dependencies**

```bash
source venv/bin/activate && pip install -q -r requirements.txt
cd frontend && npm install && cd ..
```

Expected: both finish without errors.

- [ ] **Step 3: Confirm the frontend fails without `src/lib/`**

Run: `cd frontend && npm test; cd ..`
Expected: FAIL — imports of `@/lib/api`, `@/lib/types` or `@/lib/utils` cannot be resolved.

- [ ] **Step 4: Stop `.gitignore` hiding `frontend/src/lib/`**

In `.gitignore`, replace the two lines

```
lib/
lib64/
```

with

```
/lib/
/lib64/
```

- [ ] **Step 5: Create `frontend/src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 6: Create `frontend/src/lib/types.ts`**

```ts
// Mirrors api/schemas.py field for field. Change both together.

export type RunStatus =
  | "pending"
  | "generating_list"
  | "awaiting_review"
  | "generating_media"
  | "rendering_titles"
  | "rendering_video"
  | "archiving"
  | "completed"
  | "failed"
  | "cancelled";

/** Statuses after which polling should stop. Mirrors api.runs.TERMINAL_STATUSES. */
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

/** The stages shown in the progress indicator, in order. */
export const STAGE_SEQUENCE: readonly { status: RunStatus; label: string }[] = [
  { status: "generating_list", label: "Generate list" },
  { status: "awaiting_review", label: "Review items" },
  { status: "generating_media", label: "Images & audio" },
  { status: "rendering_titles", label: "Titled images" },
  { status: "rendering_video", label: "Render video" },
  { status: "archiving", label: "Archive" },
];

export interface ItemPayload {
  title: string;
  description: string;
  image_prompts: string[];
}

export interface AssetStatus {
  label: string;
  ok: boolean;
  error: string | null;
}

export interface RunSummary {
  id: string;
  topic: string;
  num_items: number;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  review_items: boolean;
  overrides: Record<string, string | number>;
  items: ItemPayload[];
  assets: AssetStatus[];
  asset_total: number;
  logs: string[];
  error: string | null;
  video_url: string | null;
  archive_slug: string | null;
}

export interface CreateRunRequest {
  topic: string;
  num_items: number;
  review_items: boolean;
  overrides: Record<string, string | number>;
}

export interface ConfigField {
  name: string;
  type: "int" | "str";
  choices: string[] | null;
  description: string;
}

export interface ConfigPayload {
  values: Record<string, string | number>;
  overridable: ConfigField[];
}

export interface ArchiveSummary {
  slug: string;
  item_count: number;
  image_count: number;
  audio_count: number;
  has_video: boolean;
  modified_at: string;
}

export interface ArchiveItem {
  title: string;
  description: string;
  image_prompts: string[];
  image_urls: string[];
  titled_image_urls: string[];
  audio_url: string | null;
}

export interface ArchiveDetail {
  slug: string;
  video_url: string | null;
  items: ArchiveItem[];
}
```

- [ ] **Step 7: Create `frontend/src/lib/api.ts`**

```ts
import type {
  ArchiveDetail,
  ArchiveSummary,
  ConfigPayload,
  CreateRunRequest,
  ItemPayload,
  RunDetail,
  RunSummary,
} from "./types";

/** An error the server reported, carrying its status so callers can branch. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    // FastAPI puts the message in `detail`; validation errors make it an array.
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((entry) => entry.msg ?? String(entry)).join(", ")
          : response.statusText || `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const getConfig = () => request<ConfigPayload>("/config");

export const listRuns = () => request<RunSummary[]>("/runs");

export const createRun = (payload: CreateRunRequest) =>
  request<RunDetail>("/runs", { method: "POST", body: JSON.stringify(payload) });

export const getRun = (runId: string) => request<RunDetail>(`/runs/${runId}`);

export const approveItems = (runId: string, items: ItemPayload[]) =>
  request<RunDetail>(`/runs/${runId}/items`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });

export const cancelRun = (runId: string) =>
  request<RunDetail>(`/runs/${runId}/cancel`, { method: "POST" });

export const listArchives = () => request<ArchiveSummary[]>("/archives");

export const getArchive = (slug: string) =>
  request<ArchiveDetail>(`/archives/${slug}`);
```

- [ ] **Step 8: Create `frontend/src/lib/api.test.ts`**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, approveItems, createRun, getRun, listArchives } from "./api";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("posts a new run to /api/runs", async () => {
    const fetchMock = mockFetch(201, { id: "abc", topic: "Birds" });
    const run = await createRun({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
    });

    expect(run.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
    });
  });

  it("gets one run by id", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await getRun("abc");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/runs/abc");
  });

  it("wraps the server's detail message in an ApiError", async () => {
    mockFetch(409, { detail: "run abc is still generating_media" });
    await expect(getRun("abc")).rejects.toThrowError(ApiError);
    await expect(getRun("abc")).rejects.toThrow("run abc is still generating_media");
  });

  it("sends approved items under an items key", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await approveItems("abc", [
      { title: "Moa", description: "d", image_prompts: ["x"] },
    ]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      items: [{ title: "Moa", description: "d", image_prompts: ["x"] }],
    });
  });

  it("lists archives", async () => {
    const fetchMock = mockFetch(200, []);
    expect(await listArchives()).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/archives");
  });
});
```

- [ ] **Step 9: Run every suite**

```bash
cd frontend && npm test && npm run build && cd ..
source venv/bin/activate && pytest -q
```

Expected: vitest PASS, the build type-checks and emits `frontend/dist/`, pytest PASS (including the one `slow` end-to-end render, about 30 seconds).

- [ ] **Step 10: Commit**

```bash
git add .gitignore frontend/src/lib
git commit -m "fix: commit the frontend API client that .gitignore was hiding

The bare lib/ rule matched frontend/src/lib/, so the typed client the
pages import was never tracked. Anchor the rule to the repo root and add
the list-format client.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Production image preset in the backend

**Files:**
- Modify: `config.py` (after the `IMAGE_QUALITY` line)
- Modify: `api/config_view.py` (`effective_config`, new `run_overrides`)
- Modify: `api/runs.py` (`Run`, `RunStore.start`, `RunStore._execute`)
- Modify: `api/schemas.py` (`RunDetailPayload`, `CreateRunRequest`, `ConfigPayload`, `config_payload`, `run_detail`)
- Modify: `api/routes.py` (`create_run`)
- Test: `tests/test_config.py`, `tests/api/test_config_view.py`, `tests/api/test_runs.py`, `tests/api/test_routes.py`

**Interfaces:**
- Consumes: `api.config_view.apply_overrides(overrides: dict[str, Any])` context manager; `RunStore.start(topic, num_items, *, review_items, overrides)`.
- Produces:
  - `config.PRODUCTION_IMAGE_SETTINGS: dict[str, str]`
  - `api.config_view.run_overrides(overrides: dict[str, Any], production_models: bool) -> dict[str, Any]`
  - `RunStore.start(topic, num_items, *, review_items, overrides, production_models: bool = False) -> Run`
  - `Run.production_models: bool`
  - `POST /api/runs` body field `production_models: bool = False`
  - Run detail JSON field `production_models: bool`
  - `GET /api/config` JSON field `production_image_settings: dict[str, str]`

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_default_image_models_are_the_cheap_ones():
    module = importlib.reload(config)
    assert module.IMAGE_MODEL == "gpt-image-1"
    assert module.IMAGE_SIZE == "1024x1024"
    assert module.IMAGE_QUALITY == "medium"


def test_production_image_settings_select_the_better_model():
    assert config.PRODUCTION_IMAGE_SETTINGS == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "high",
    }


def test_production_image_settings_name_real_constants():
    for name in config.PRODUCTION_IMAGE_SETTINGS:
        assert hasattr(config, name)


def test_production_image_settings_keep_the_image_square():
    # The title is drawn beneath the image; a portrait image pushes it off
    # the bottom of the 1920px frame.
    assert "IMAGE_SIZE" not in config.PRODUCTION_IMAGE_SETTINGS
```

If `tests/test_config.py` does not already `import importlib`, add it at the top.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'PRODUCTION_IMAGE_SETTINGS'`

- [ ] **Step 3: Add the preset to `config.py`**

Directly after the `IMAGE_QUALITY = _env_str("IMAGE_QUALITY", "medium")` line:

```python

# What the web UI's "Production models" option swaps in for one run. The
# defaults above are the cheap ones, for iterating. IMAGE_SIZE is left out on
# purpose: the title is drawn beneath the image, and a portrait image pushes
# it off the bottom of the frame.
PRODUCTION_IMAGE_SETTINGS = {
    "IMAGE_MODEL": "gpt-image-2",
    "IMAGE_QUALITY": "high",
}
```

- [ ] **Step 4: Run them to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing config-view tests**

In `tests/api/test_config_view.py`, extend the import block to

```python
import base64
from types import SimpleNamespace

import pytest

import config
from api.config_view import (
    OVERRIDABLE,
    ConfigOverrideError,
    apply_overrides,
    effective_config,
    run_overrides,
    validate_overrides,
)
from scripts.ai.generate_images.utils import generate_image
```

and append:

```python
def test_effective_config_leaves_out_the_production_preset():
    # The config page renders every value as a scalar.
    assert "PRODUCTION_IMAGE_SETTINGS" not in effective_config()


def test_run_overrides_are_untouched_without_production_models():
    assert run_overrides({"MAX_RETRIES": 2}, False) == {"MAX_RETRIES": 2}


def test_run_overrides_add_the_production_preset():
    assert run_overrides({"MAX_RETRIES": 2}, True) == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "high",
        "MAX_RETRIES": 2,
    }


def test_an_explicit_override_beats_the_production_preset():
    assert run_overrides({"IMAGE_QUALITY": "low"}, True) == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "low",
    }


def test_run_overrides_do_not_mutate_their_input_or_the_preset():
    given = {"IMAGE_QUALITY": "low"}
    run_overrides(given, True)
    assert given == {"IMAGE_QUALITY": "low"}
    assert config.PRODUCTION_IMAGE_SETTINGS["IMAGE_QUALITY"] == "high"


def test_the_production_preset_beats_an_image_model_pinned_by_the_environment(
    monkeypatch,
):
    monkeypatch.setattr(config, "IMAGE_MODEL", "some-pinned-model")
    with apply_overrides(run_overrides({}, True)):
        assert config.IMAGE_MODEL == "gpt-image-2"
    assert config.IMAGE_MODEL == "some-pinned-model"


def test_the_production_preset_reaches_the_image_api(tmp_path):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        encoded = base64.b64encode(b"png-bytes").decode()
        return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])

    client = SimpleNamespace(images=SimpleNamespace(generate=generate))
    square = config.IMAGE_SIZE

    with apply_overrides(run_overrides({}, True)):
        generate_image("a dodo", tmp_path / "dodo.png", client=client)

    assert calls[0]["model"] == "gpt-image-2"
    assert calls[0]["quality"] == "high"
    assert calls[0]["size"] == square
```

- [ ] **Step 6: Run them to verify they fail**

Run: `pytest tests/api/test_config_view.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_overrides'`

- [ ] **Step 7: Implement `run_overrides` and the scalar filter in `api/config_view.py`**

Replace `effective_config` with:

```python
def effective_config() -> dict[str, Any]:
    """Every scalar config constant currently in force, overrides included.

    Presets such as `PRODUCTION_IMAGE_SETTINGS` are not settings in their own
    right and the UI renders each value as plain text, so they are left out.
    """
    values: dict[str, Any] = {}
    for name in dir(config):
        if not name.isupper() or name.startswith("_"):
            continue
        value = getattr(config, name)
        if isinstance(value, (str, int, float)):
            values[name] = value
    return values
```

Add, directly above `apply_overrides`:

```python
def run_overrides(
    overrides: dict[str, Any], production_models: bool
) -> dict[str, Any]:
    """The constants to swap in for one run.

    The production preset sits underneath whatever was named explicitly, which
    is what lets a production run dial one knob back.
    """
    if not production_models:
        return dict(overrides)
    return {**config.PRODUCTION_IMAGE_SETTINGS, **overrides}
```

- [ ] **Step 8: Run them to verify they pass**

Run: `pytest tests/api/test_config_view.py -q`
Expected: PASS

- [ ] **Step 9: Write the failing run-store tests**

In `tests/api/test_runs.py`, add `import config` beside the other imports and append:

```python
def capture_image_settings(monkeypatch):
    """Record the image settings in force when the media stage runs."""
    seen = {}

    def media_stage(items, client=None, log=print, on_asset=None):
        seen["model"] = config.IMAGE_MODEL
        seen["quality"] = config.IMAGE_QUALITY

    monkeypatch.setattr("api.runs.pipeline.generate_media_stage", media_stage)
    return seen


def test_a_production_run_generates_with_the_production_image_settings(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)
    seen = capture_image_settings(monkeypatch)
    before = (config.IMAGE_MODEL, config.IMAGE_QUALITY)

    store = RunStore()
    run = store.start(
        "Birds", 1, review_items=False, overrides={}, production_models=True
    )
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert finished.production_models is True
    assert seen == {"model": "gpt-image-2", "quality": "high"}
    # Only what the user typed is recorded as an override.
    assert finished.overrides == {}
    assert (config.IMAGE_MODEL, config.IMAGE_QUALITY) == before


def test_a_run_is_cheap_unless_production_models_is_asked_for(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)
    seen = capture_image_settings(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    assert store.get(run.id).production_models is False
    assert seen == {"model": config.IMAGE_MODEL, "quality": config.IMAGE_QUALITY}
    assert seen["model"] != "gpt-image-2"


def test_an_override_beats_the_preset_inside_a_production_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)
    seen = capture_image_settings(monkeypatch)

    store = RunStore()
    store.start(
        "Birds",
        1,
        review_items=False,
        overrides={"IMAGE_QUALITY": "low"},
        production_models=True,
    )
    store.wait_for_idle()

    assert seen == {"model": "gpt-image-2", "quality": "low"}


def test_a_reviewed_production_run_keeps_the_preset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)
    seen = capture_image_settings(monkeypatch)

    store = RunStore()
    run = store.start(
        "Birds", 1, review_items=True, overrides={}, production_models=True
    )
    store.wait_for_status(run.id, "awaiting_review")
    store.approve_items(run.id, one_item())
    store.wait_for_idle()

    assert store.get(run.id).status == "completed"
    assert seen == {"model": "gpt-image-2", "quality": "high"}


def test_a_failed_production_run_restores_the_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)
    before = (config.IMAGE_MODEL, config.IMAGE_QUALITY)

    def explode(items, client=None, log=print, on_asset=None):
        raise RuntimeError("no access to gpt-image-2")

    monkeypatch.setattr("api.runs.pipeline.generate_media_stage", explode)

    store = RunStore()
    run = store.start(
        "Birds", 1, review_items=False, overrides={}, production_models=True
    )
    store.wait_for_idle()

    failed = store.get(run.id)
    assert failed.status == "failed"
    assert "no access to gpt-image-2" in failed.error
    assert (config.IMAGE_MODEL, config.IMAGE_QUALITY) == before
```

- [ ] **Step 10: Run them to verify they fail**

Run: `pytest tests/api/test_runs.py -q`
Expected: FAIL — `TypeError: RunStore.start() got an unexpected keyword argument 'production_models'`

- [ ] **Step 11: Carry the flag through `api/runs.py`**

Change the import:

```python
from api.config_view import apply_overrides, run_overrides
```

In the `Run` dataclass, add the field directly after `overrides`:

```python
    overrides: dict[str, Any]
    production_models: bool = False
    status: str = STATUS_PENDING
```

In `RunStore.start`, extend the signature and the `Run(...)` call:

```python
    def start(
        self,
        topic: str,
        num_items: int,
        *,
        review_items: bool,
        overrides: dict[str, Any],
        production_models: bool = False,
    ) -> Run:
```

```python
            run = Run(
                id=uuid.uuid4().hex[:12],
                topic=topic,
                num_items=num_items,
                review_items=review_items,
                overrides=dict(overrides),
                production_models=production_models,
            )
```

In `RunStore._execute`, replace `with apply_overrides(run.overrides):` with:

```python
            with apply_overrides(
                run_overrides(run.overrides, run.production_models)
            ):
```

and add one log line as the first statement inside that block, before `self._check_cancelled(gate)`:

```python
                if run.production_models:
                    log(
                        f"Production models: images use {config.IMAGE_MODEL} "
                        f"at {config.IMAGE_QUALITY} quality."
                    )
```

Add `import config` to the imports at the top of `api/runs.py`, beside `import pipeline`.

- [ ] **Step 12: Run them to verify they pass**

Run: `pytest tests/api/test_runs.py -q`
Expected: PASS

- [ ] **Step 13: Write the failing route tests**

Append to `tests/api/test_routes.py`:

```python
def test_config_reports_the_production_image_settings(client):
    payload = client.get("/api/config").json()
    assert payload["production_image_settings"] == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "high",
    }
    assert "PRODUCTION_IMAGE_SETTINGS" not in payload["values"]


def test_creating_a_production_run_echoes_the_flag(client, monkeypatch):
    stub_stages(monkeypatch)
    response = client.post(
        "/api/runs",
        json={"topic": "Birds", "num_items": 1, "production_models": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["production_models"] is True
    assert body["overrides"] == {}
    assert client.get(f"/api/runs/{body['id']}").json()["production_models"] is True


def test_creating_a_run_defaults_to_cheap_models(client, monkeypatch):
    stub_stages(monkeypatch)
    response = client.post("/api/runs", json={"topic": "Birds", "num_items": 1})
    assert response.status_code == 201
    assert response.json()["production_models"] is False


def test_creating_a_run_rejects_a_null_production_flag(client):
    response = client.post(
        "/api/runs",
        json={"topic": "Birds", "num_items": 1, "production_models": None},
    )
    assert response.status_code == 422
```

- [ ] **Step 14: Run them to verify they fail**

Run: `pytest tests/api/test_routes.py -q`
Expected: FAIL — `KeyError: 'production_image_settings'` and `KeyError: 'production_models'`

- [ ] **Step 15: Extend the wire contract in `api/schemas.py`**

Add `import config` beside the other imports.

`RunDetailPayload` gains one field after `overrides`:

```python
class RunDetailPayload(RunSummaryPayload):
    review_items: bool
    overrides: dict[str, Any]
    production_models: bool
    items: list[ItemPayload]
```

`CreateRunRequest` gains one field after `overrides`:

```python
    overrides: dict[str, Any] = Field(default_factory=dict)
    production_models: bool = False
```

`ConfigPayload` becomes:

```python
class ConfigPayload(BaseModel):
    values: dict[str, Any]
    overridable: list[ConfigFieldPayload]
    production_image_settings: dict[str, str]
```

In `config_payload()`, pass the preset as a third argument:

```python
        production_image_settings=dict(config.PRODUCTION_IMAGE_SETTINGS),
```

In `run_detail()`, add one keyword after `overrides=run.overrides,`:

```python
        production_models=run.production_models,
```

- [ ] **Step 16: Pass the flag through `api/routes.py`**

In `create_run`, extend the `store.start(...)` call:

```python
        run = store.start(
            payload.topic,
            payload.num_items,
            review_items=payload.review_items,
            overrides=overrides,
            production_models=payload.production_models,
        )
```

- [ ] **Step 17: Run the whole backend suite**

Run: `pytest -q`
Expected: PASS, including the `slow` end-to-end test.

- [ ] **Step 18: Commit**

```bash
git add config.py api tests
git commit -m "feat: add a production image preset a run can opt into

Cheap models stay the default. A run started with production_models
generates its images with gpt-image-2 at high quality; explicit per-run
overrides still win, and config is restored when the run ends.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: "Production models" in the web UI, and the docs

**Files:**
- Modify: `frontend/src/lib/types.ts` (`RunDetail`, `CreateRunRequest`, `ConfigPayload`)
- Modify: `frontend/src/lib/api.test.ts` (the `createRun` test)
- Modify: `frontend/src/pages/NewRunPage.tsx`, `frontend/src/pages/NewRunPage.test.tsx`
- Modify: `frontend/src/pages/RunPage.tsx`, `frontend/src/pages/RunPage.test.tsx`
- Modify: `README.md` (Configuration and web UI sections)

**Interfaces:**
- Consumes: `POST /api/runs` body field `production_models: boolean`; run detail field `production_models: boolean`; `GET /api/config` field `production_image_settings: Record<string, string>` (Task 2).
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Write the failing New Run tests**

In `frontend/src/pages/NewRunPage.test.tsx`:

Add the preset to the `config` fixture:

```ts
const config = {
  values: { IMAGE_QUALITY: "medium", MAX_RETRIES: 5 },
  overridable: [
    {
      name: "IMAGE_QUALITY",
      type: "str",
      choices: ["low", "medium", "high"],
      description: "Higher costs more.",
    },
    { name: "MAX_RETRIES", type: "int", choices: null, description: "Attempts." },
  ],
  production_image_settings: { IMAGE_MODEL: "gpt-image-2", IMAGE_QUALITY: "high" },
};
```

Replace `mockApi` so the config request can be made to fail:

```ts
function mockApi(
  createResponse: { status: number; body: unknown },
  options: { configFails?: boolean } = {},
) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return {
        ok: createResponse.status < 300,
        status: createResponse.status,
        statusText: "",
        json: async () => createResponse.body,
      };
    }
    if (options.configFails) {
      return {
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => ({ detail: "boom" }),
      };
    }
    return { ok: true, status: 200, statusText: "", json: async () => config };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
```

In the existing test `creates a run and navigates to it`, change the expected body to:

```ts
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      topic: "Extinct animals",
      num_items: 5,
      review_items: false,
      overrides: {},
      production_models: false,
    });
```

Add three tests inside the `describe` block:

```ts
  it("sends production_models when the option is ticked", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.click(screen.getByLabelText(/production models/i));
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    const body = JSON.parse(post[1]!.body as string);
    expect(body.production_models).toBe(true);
    // The preset is applied by the server, not smuggled in as overrides.
    expect(body.overrides).toEqual({});
  });

  it("says what the production option switches to", async () => {
    mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    expect(
      await screen.findByText(/gpt-image-2, high quality/i),
    ).toBeInTheDocument();
  });

  it("still offers production models when the config request fails", async () => {
    const fetchMock = mockApi(
      { status: 201, body: { id: "abc" } },
      { configFails: true },
    );
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.click(screen.getByLabelText(/production models/i));
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string).production_models).toBe(true);
  });
```

- [ ] **Step 2: Write the failing Run page tests**

In `frontend/src/pages/RunPage.test.tsx`, add `production_models: false,` to the `base` object after `overrides: {},` and add two tests inside the `describe` block:

```ts
  it("marks a run that used production models", async () => {
    mockRun({ ...base, status: "generating_media", production_models: true });
    renderPage();
    expect(await screen.findByText("Birds")).toBeInTheDocument();
    expect(screen.getByText("Production models")).toBeInTheDocument();
  });

  it("does not mark a run on the default models", async () => {
    mockRun({ ...base, status: "generating_media" });
    renderPage();
    expect(await screen.findByText("Birds")).toBeInTheDocument();
    expect(screen.queryByText("Production models")).toBeNull();
  });
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd frontend && npm test; cd ..`
Expected: FAIL — no element labelled "production models", no text "gpt-image-2, high quality", no text "Production models", and the `creates a run` body lacks `production_models`.

- [ ] **Step 4: Extend `frontend/src/lib/types.ts`**

`RunDetail` gains one field after `overrides`:

```ts
  overrides: Record<string, string | number>;
  production_models: boolean;
```

`CreateRunRequest` becomes:

```ts
export interface CreateRunRequest {
  topic: string;
  num_items: number;
  review_items: boolean;
  overrides: Record<string, string | number>;
  production_models: boolean;
}
```

`ConfigPayload` becomes:

```ts
export interface ConfigPayload {
  values: Record<string, string | number>;
  overridable: ConfigField[];
  production_image_settings: Record<string, string>;
}
```

- [ ] **Step 5: Keep `frontend/src/lib/api.test.ts` type-correct**

In the test `posts a new run to /api/runs`, add `production_models: false,` to both the `createRun({...})` argument and the expected body:

```ts
    const run = await createRun({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
      production_models: false,
    });
```

```ts
    expect(JSON.parse(init.body)).toEqual({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
      production_models: false,
    });
```

- [ ] **Step 6: Add the option to `frontend/src/pages/NewRunPage.tsx`**

Above `export default function NewRunPage()`, add:

```tsx
/** One line saying what the production option switches to, or null. */
function describeProduction(settings: Record<string, string>): string | null {
  const parts = [
    settings.IMAGE_MODEL,
    settings.IMAGE_QUALITY && `${settings.IMAGE_QUALITY} quality`,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return `Images: ${parts.join(", ")}. Slower and more expensive.`;
}
```

Add two state hooks after the `reviewItems` one:

```tsx
  const [productionModels, setProductionModels] = useState(false);
  const [production, setProduction] = useState<Record<string, string>>({});
```

In the `getConfig().then(...)` callback, store the preset:

```tsx
      .then((payload) => {
        setFields(payload.overridable);
        setCurrent(payload.values);
        setProduction(payload.production_image_settings ?? {});
      })
```

In `onSubmit`, send the flag:

```tsx
      const run = await createRun({
        topic: topic.trim(),
        num_items: numItems,
        review_items: reviewItems,
        overrides: filled,
        production_models: productionModels,
      });
```

Directly after the closing `</div>` of the review checkbox row (the `<div className="flex items-center gap-2">` holding `id="review"`), add:

```tsx
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Checkbox
                id="production"
                checked={productionModels}
                onCheckedChange={(checked) => setProductionModels(checked === true)}
              />
              <Label htmlFor="production" className="font-normal">
                Production models
              </Label>
            </div>
            {describeProduction(production) && (
              <p className="text-xs text-muted-foreground">
                {describeProduction(production)}
              </p>
            )}
          </div>
```

- [ ] **Step 7: Add the badge to `frontend/src/pages/RunPage.tsx`**

Add the import beside the other `ui` imports:

```tsx
import { Badge } from "@/components/ui/badge";
```

Replace the header's text block

```tsx
        <div>
          <h1 className="text-xl font-semibold">{run.topic}</h1>
          <p className="text-sm text-muted-foreground">
            {run.num_items} items · {run.status}
          </p>
        </div>
```

with

```tsx
        <div>
          <h1 className="text-xl font-semibold">{run.topic}</h1>
          <p className="text-sm text-muted-foreground">
            {run.num_items} items · {run.status}
          </p>
          {run.production_models && (
            <Badge variant="secondary" className="mt-1">
              Production models
            </Badge>
          )}
        </div>
```

- [ ] **Step 8: Run the frontend suite and the build**

Run: `cd frontend && npm test && npm run build && cd ..`
Expected: vitest PASS; the build type-checks with no errors.

- [ ] **Step 9: Document it in `README.md`**

In the "The UI can:" list of the "Run the Web UI" section, add a bullet after the overrides bullet:

```markdown
- switch a single run to production image models with the **Production
  models** checkbox on the New Run page
```

Directly before the `**Only one run can be active at a time.**` paragraph, add:

```markdown
#### Production models

The defaults are the cheap models, for iterating: `gpt-4.1-mini` writes the
list, `gpt-image-1` at `medium` quality draws the images and
`gpt-4o-mini-tts` narrates. Ticking **Production models** generates that run's
images with `gpt-image-2` at `high` quality instead. It is slower and costs
more, and it changes image generation only.

Anything you type into the per-run override fields still wins, so a production
run with `IMAGE_QUALITY` set to `low` uses `gpt-image-2` at `low`. The preset
lives in `PRODUCTION_IMAGE_SETTINGS` in `config.py`. The CLI always uses the
defaults; set `IMAGE_MODEL` and `IMAGE_QUALITY` in `.env` to change them there.
```

- [ ] **Step 10: Run every suite one last time**

```bash
source venv/bin/activate && pytest -q
cd frontend && npm test && npm run build && cd ..
```

Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add frontend/src README.md
git commit -m "feat: offer production models on the New Run page

A checkbox sends production_models with the run, the helper line is built
from the preset the server reports, and the run page badges a run that
used it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
