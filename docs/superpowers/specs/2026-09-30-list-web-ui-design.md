# Web UI and production image models for the list pipeline

Date: 2026-09-30
Branch: `feat/list-web-ui` (off `main`)

## Goal

`main` keeps the list format — a topic becomes N items, each with a title, a
description and three images — and gains the web UI that so far exists only on
`feat/sectioned-scripts`. Cheap models stay the default. A "Production models"
option on the New Run page switches image generation to better settings for
that one run.

## Out of scope

- The sectioned-script format, story beats, style sheets and chained images.
- Changing the text model (`gpt-4.1-mini`) or the narration model
  (`gpt-4o-mini-tts`).
- Portrait images. The list format draws the item title beneath the image; a
  1024x1536 image scaled to the 1080 frame width is 1620px tall and pushes the
  title past the 1920px frame bottom.
- A CLI flag or environment variable for the production preset. The CLI can
  still set `IMAGE_MODEL` and `IMAGE_QUALITY` through `.env`.

## Part 1: bring the list-era web UI onto the branch

`feat/sectioned-scripts` built the web UI before it replaced the list format.
Commit `9c3cea3` is `main` plus 18 commits, and `main` is its ancestor, so the
branch fast-forwards to it. That brings:

- `api/` — FastAPI app, run state machine with a background worker, config
  view with per-run overrides, archive reader, routes and schemas.
- `frontend/` — Vite + React + TypeScript app: New Run, run progress with
  assets and logs, item review before media generation, archives browser,
  config page.
- `pipeline.py` split into independently callable stages; `run_pipeline` and
  the CLI behave as before.
- `fastapi`, `uvicorn[standard]` and `httpx` in `requirements.txt`.
- Backend tests under `tests/api/` and frontend vitest suites.
- README section on running the web UI.

### Restoring `frontend/src/lib/`

At `9c3cea3` the directory `frontend/src/lib/` was never committed: the root
`.gitignore` has a bare `lib/` rule that matched it. The files were first
committed in `0687dc2`, by which point they described story beats rather than
list items, so that version cannot be used.

- Change `.gitignore` rules `lib/` and `lib64/` to `/lib/` and `/lib64/`.
- Recreate `types.ts`, `api.ts` and `api.test.ts` from the full listings in
  `docs/superpowers/plans/2026-09-03-web-frontend.md` (Task 8), which are the
  list-format originals. `types.ts` must mirror `api/schemas.py` at `9c3cea3`
  field for field.
- Take `utils.ts` (the shadcn `cn` helper) from `0687dc2`; it has no
  dependence on the item shape.

## Part 2: production image models

### Config

`config.py` gains one constant beside the image settings:

```python
PRODUCTION_IMAGE_SETTINGS = {
    "IMAGE_MODEL": "gpt-image-2",
    "IMAGE_QUALITY": "high",
}
```

Defaults are unchanged: `gpt-image-1`, `1024x1024`, `medium`. The preset is
not read from the environment.

`effective_config()` collects every upper-case name in `config` and the UI
renders each as a scalar, so it now skips values that are not `str`, `int` or
`float`. The preset travels separately: `ConfigPayload` gains
`production_image_settings: dict[str, str]`.

### API

- `CreateRunRequest` gains `production_models: bool = False`.
- `RunStore.start` takes `production_models` and stores it on `Run`.
- `api/config_view.py` gains `run_overrides(overrides, production_models)`:
  when the flag is set it returns the preset with the explicit overrides laid
  on top, otherwise the overrides unchanged. The worker passes its result to
  `apply_overrides`, so the preset is swapped in for the run and restored
  afterwards by the existing mechanism.
- Precedence: explicit per-run override > production preset > `config`
  default. `production_models: true` with `IMAGE_QUALITY: "low"` yields
  `gpt-image-2` at `low`.
- `Run.overrides` keeps only what the user typed; `RunDetailPayload` gains
  `production_models: bool` so the two stay distinguishable.

### Frontend

- `types.ts`: `production_models` on `CreateRunRequest` and `RunDetail`, and
  `production_image_settings` on `ConfigPayload`.
- New Run page: a "Production models" checkbox under the review checkbox.
  Its helper line is built from `production_image_settings` returned by
  `/api/config` (for example "Images: gpt-image-2, high quality. Slower and
  more expensive."), so the text cannot drift from the backend. If the config
  request fails the checkbox still works, without the helper line.
- Run page: a "Production models" badge when the run used the preset.

### Error handling

No new failure modes. An account without access to `gpt-image-2` fails in the
media stage like any other image error and is reported per asset, as today.

## Testing

Backend (pytest, fake OpenAI client, no network):

- `run_overrides` returns the preset when the flag is set, the bare overrides
  when it is not, and lets an explicit override beat the preset.
- A run started with `production_models` calls the image API with
  `gpt-image-2` / `high`; a run without it uses `gpt-image-1` / `medium`.
- `config` values are restored after a production run.
- `POST /api/runs` accepts the flag and the run detail echoes it.
- `config.PRODUCTION_IMAGE_SETTINGS` names only real config constants.
- `GET /api/config` returns the preset in `production_image_settings` and
  keeps it out of `values`.

Frontend (vitest):

- Ticking the checkbox sends `production_models: true`; leaving it sends
  `false`.
- The helper line reflects the preset from the config payload.
- The run page shows the badge only for production runs.

Whole-suite gates: `pytest`, `npm test`, `npm run build`.

## Documentation

README: add the production option to the web UI section and note the defaults
are the cheap models.
