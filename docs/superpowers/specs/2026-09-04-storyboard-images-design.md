# Storyboard images: sequential frames that tell one story per item

## Problem

Each item's images are independent. `generate_list` asks for three unrelated
prompts — "a straightforward representation", "hilariously funny", "a different
style or perspective" — and `image_jobs` fires them as unrelated one-shot
`images.generate` calls. `build_item_clip` then splits the narration into equal
segments and shows one image per segment.

The result is three disconnected pictures over a continuous script. Nothing
carries from one frame to the next, and no frame is tied to the words playing
under it.

## Goal

Each item becomes a short visual story: a sequence of stick-figure line
drawings, each continuing the last, each landing on the narration it
illustrates. Talk about a scientist and you see the scientist; talk about the
experiment and the same scientist is now beside the apparatus.

Scope is per item. Item 3's frames continue from each other and have no
relationship to item 2's, which preserves the existing "Top 5 X" list format.

## Design

### 1. Data model

An item becomes a style sheet plus an ordered list of beats.

```json
{
  "title": "The Cavendish Experiment",
  "style": "A reclusive stick-figure scientist: round head, wild scribble hair, round glasses, long coat. Plain white background, wooden bench.",
  "description": "<derived: the beat narrations joined>",
  "beats": [
    {
      "narration": "In 1798 a reclusive scientist set out to weigh the world.",
      "prompt": "The scientist stands alone in an empty room, hands behind his back."
    },
    {
      "narration": "He hung two lead spheres from a wire inside a sealed box.",
      "prompt": "Same scientist, now beside a tall box; two circles hang from a thread inside."
    },
    {
      "narration": "Their faint pull let him calculate Earth's mass to within one percent.",
      "prompt": "Same scientist, same box, now leaning in with a notebook; a curved arrow shows the spheres drawn together."
    }
  ]
}
```

Three decisions:

**`description` is derived, not authored.** `parse_items` computes it by
joining the beat narrations, and `save_items` writes the computed value. This
guarantees the spoken script and the frames cannot drift apart, and it is what
makes the proportional timing in section 3 exact rather than approximate. Every
existing consumer of `description` — `Item.narration`, the TTS call, the
archive browser — keeps working unchanged.

**`style` is per-item and model-authored.** It describes the recurring figure
and setting so every one of that item's prompts can be rendered consistently.
It is prepended to each of the item's prompts. The global `STORYBOARD_STYLE`
from `config.py` is prepended in front of that.

**Beat count reuses `IMAGE_PROMPTS_PER_ITEM`.** One sentence of narration per
beat means the single existing knob controls story length and frame count
together. It is already in `OVERRIDABLE` and already rendered by the run form,
so per-run control of story length costs no new API or frontend surface.

A consequence worth stating: at the default of 3, narration goes from the
current two sentences to three, so each item runs roughly 4 seconds longer.
Five items still fit comfortably inside a 60-second Short. Lower the override
to 2 for the old length.

### 2. Backwards compatibility

`parse_items` accepts both shapes:

- `beats` present — the new path.
- only `image_prompts` present — the old path. One beat per prompt, each with
  an empty `narration`, and `description` taken from the stored field rather
  than derived.

`Item.image_prompts` survives as a property deriving the prompts from the
beats, so `generate_images`, `archives.py` and `save_to_generated_data` need no
change to their filename or counting logic. Every existing `generated_data/`
archive keeps loading and rendering.

### 3. List generation

`generate_list` gets a new JSON schema carrying `style` and `beats`, and a
rewritten user message. The prompt instructs the model to:

- Write a `style` line naming the recurring figure(s) and setting concretely
  enough to be redrawn identically.
- Emit exactly `IMAGE_PROMPTS_PER_ITEM` beats.
- Give each beat one sentence of `narration`, such that the sentences read as
  continuous prose in order.
- Give each beat a `prompt` describing the drawing as a continuation of the
  previous one — same character, same setting, one thing added or changed.

The existing safety and copyright guidance in the user message is retained
verbatim.

`parse_items` validates the beat count against `IMAGE_PROMPTS_PER_ITEM`, read
at call time so a per-run override applies.

### 4. Image generation: two waves

Frames 2..N of an item depend on frame 1, so they cannot all be one flat job
list. The naive fix — one sequential job per item — would drop parallelism from
15 jobs to 5 and coarsen the progress bar from per-image to per-item.

Instead `generate_media_stage` runs two `run_all` passes over the shared pool:

- **Wave A** — every item's anchor frame via `images.generate`, plus every
  narration job. Audio rides along so it is not idle-waiting.
- **Wave B** — every follow-up frame, one job per `(item, beat 2..N)`, each
  calling `images.edit` with its item's anchor PNG as the reference image.
  Fully parallel across all items and all beats.

Wall clock is two image rounds rather than N. `media_job_total` is unchanged,
so `_begin_asset_stage` and the UI's asset progress stay per-image. Labels
become `image item 3 beat 2`.

If an item's anchor fails, its wave B jobs are skipped and recorded as failed
with that reason. The existing `missing_media` check in `pipeline.py` catches
the resulting gap and aborts the stage, as it does today.

Every prompt sent in either wave is `STORYBOARD_STYLE` + the item's `style` +
the beat's `prompt`.

### 5. Timing

`segment_bounds(total_duration, count)` becomes
`segment_bounds(total_duration, weights)`, taking a per-beat weight list and
splitting the duration proportionally. Weights are the word counts of each
beat's narration.

This is a strict generalization: equal weights produce output identical to
today, which is what old archives — beats with empty narration, hence all-zero
weights — fall back to.

`build_item_clip(item_number, image_count)` becomes
`build_item_clip(item_number, item)` so it can read the weights.
`generate_video_short` passes the item through.

The 0.2s intro and 0.5s outro silences are already inside `total_duration`, so
a proportional split stretches every frame by the same small factor. The first
frame absorbs the lead-in, the last absorbs the tail. No special-casing.

### 6. Configuration

- New `STORYBOARD_STYLE` in `config.py`: the fixed look contract — black ink
  outline drawing on a plain white background, stick-figure people with simple
  round heads, minimal interior detail, no shading, no colour, no text or
  lettering.
- Added to `config_view.OVERRIDABLE` as a `str` field, so it is tunable per run
  from the existing form.
- `IMAGE_PROMPTS_PER_ITEM` keeps its name and type; its `OverridableField`
  description is reworded to say it now sets narration length as well as frame
  count.

### 7. API and frontend

- `api/schemas.py` — new `BeatPayload {narration, prompt}`. `ItemPayload`
  becomes `{title, style, beats, description}`, where `description` is
  output-only: the server always recomputes it from the beats, so a human who
  edits a narration cannot leave a stale script behind. `ArchiveItemPayload`
  gains `style` and `beats` and keeps `image_prompts` for old archives.
- `api/routes.py` — `approve_items` logic is unchanged; still
  `parse_items(..., expected_prompts=None)`, so adding or removing a beat
  during review stays legal.
- `frontend/src/lib/types.ts` — mirrors the above, as its header comment
  requires.
- `frontend/src/components/ItemEditor.tsx` — the flat prompt list becomes
  per-beat rows (narration textarea plus prompt input), with a style textarea
  per item. Description renders as read-only text that updates live as
  narrations are edited. Add/remove beat replaces add/remove prompt.
- `frontend/src/pages/ArchiveDetailPage.tsx` — shows each beat's narration
  beside its prompt when present, falling back to the flat prompt list for
  archives written before this change.

## What this replaces

This is a replacement, not a second mode. The "straightforward / hilariously
funny / different perspective" prompt strategy is removed. There is one prompt
path, not two.

The titled-image stage is deliberately untouched. A white-background line
drawing run through `blurred_background` yields a near-white field, which is
the desired result, so no change is needed there.

## Testing

TDD, matching the existing per-module test layout.

- `tests/test_models.py` — v2 parse; v1 back-compat; derived description; beat
  count validated against `IMAGE_PROMPTS_PER_ITEM`; save/load round-trip.
- `tests/test_generate_list.py` — a fake client returning a v2 payload; the
  request schema carries `style` and `beats`; a wrong beat count raises
  `InvalidItemsError`.
- `tests/test_generate_images.py` — a fake client recording `images.generate`
  against `images.edit`; wave B passes the anchor file as the reference; the
  global style and the item style sheet prefix every prompt in both waves; an
  anchor failure marks its follow-ups failed rather than silently absent.
- `tests/test_video.py` — weighted `segment_bounds`: equal weights reproduce
  the old split exactly; unequal weights allocate proportionally; segments sum
  to the total; all-zero weights fall back to an equal split.
- `tests/test_pipeline.py` — the two-wave media stage still reports
  `media_job_total` assets; `missing_media` still aborts.
- `tests/api/` — beats round-trip through the wire contract; approving edited
  beats recomputes the description; an archive in the old shape still lists and
  renders.
- Frontend — `ItemEditor.test.tsx` covers beat editing and the derived
  description; `ArchiveDetailPage.test.tsx` covers beat display and the old
  fallback.

## Risk

The load-bearing assumption is that
`client.images.edit(model="gpt-image-1", image=[anchor], prompt=...)` accepts a
reference image and honours it as character and style guidance on the installed
SDK (openai 3.2.0).

Implementation step zero is a throwaway two-call script confirming this before
anything is built on it. The script is deleted once it has answered.

If the reference does not hold the character well enough, the fallback is the
style-contract-only approach: delete wave B and generate every frame
independently. Because the per-item style sheet is prepended to every prompt in
both waves regardless, that fallback requires no other change — sections 1, 2,
3, 5, 6 and 7 stand either way.
