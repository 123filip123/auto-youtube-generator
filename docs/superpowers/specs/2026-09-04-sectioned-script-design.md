# Sectioned scripts: one topic becomes one narrated video

## Problem

A topic currently produces a *list*. `generate_list` asks for N items, each
with its own title, style sheet and six beats; each item gets its own narration
file and its own visual story, and the video is those N stories concatenated.
The format is "Top 5 X".

That is not the format we want to publish. A short that performs is one
continuous argument — a hook that stops the scroll, a setup, a turn, the
evidence, a payoff, a call to action — narrated as prose, with images laid over
it as a visual track. The list format cannot express that shape. Its unit of
composition is the item, and items are by construction unrelated to each other.

The current model also welds the script to the pictures. One beat is one
sentence is one image, so the writing is constrained to image-sized sentences,
and frame duration is constrained by how short a spoken sentence can be — a
floor of about three seconds, because the voice leaves ~1.6s of silence after
every sentence no matter how few words precede it.

## Goal

A topic and a target duration produce one script, divided into free-form
sections. Each section is a paragraph of narration. Images are laid over that
narration at roughly one per 2.5 seconds, generated as a chain within each
section so the frames read as motion, and reset at each section boundary so the
cut lands with the editorial beat.

The illustrative target:

```
[HOOK - 0:00-0:05]
"Your dog's ancestor could've killed you. So how did we end up with THIS—"

[SETUP - 0:05-0:20]
Somewhere between 15,000 and 40,000 years ago, gray wolves started hanging
around human camps. Not because we tamed them — because the bravest, least
fearful wolves realized our trash piles were basically a buffet.

...
```

The list format is **replaced**, not kept alongside. `Item` and `Beat` are
removed.

## Design

### 1. Data model

`models.py` drops `Item` and `Beat` for:

```python
@dataclass(frozen=True)
class Section:
    label: str                    # free-form: "HOOK", "WAIT, WHAT?"
    narration: str                # the whole spoken paragraph
    prompts: tuple[str, ...]      # one image prompt per shot

@dataclass(frozen=True)
class Script:
    topic: str
    title: str                    # the YouTube title, from call 1
    style: str                    # global style sheet, from call 2
    sections: tuple[Section, ...]
```

Saved to `outputs/json_output/script.json`:

```json
{
  "topic": "how dogs evolved from wolves",
  "title": "Wolves Domesticated Themselves",
  "style": "A lean grey-blue wolf with amber eyes and a notched left ear...",
  "sections": [
    {
      "label": "HOOK",
      "narration": "Your dog's ancestor could've killed you. So how did we end up with this?",
      "start": 0.0,
      "end": 5.2,
      "prompts": [
        "A lean grey-blue wolf stands square on a bare white ground, teeth bared, amber eyes fixed forward.",
        "The same ground, the same amber eyes, but the figure is now a round-bodied golden dog mid-roll, tongue out, legs in the air."
      ]
    }
  ]
}
```

Four decisions:

**Narration is per section, not per shot.** This is the inversion that makes
the target format reachable. Today the script is written to fit the pictures;
here a section is written as prose and the shots are laid over it. It also
frees frame duration from spoken-sentence length, which is what puts 2.5s
within reach — the three-second floor existed only because one frame had to
hold one whole sentence, pause included.

**Shot count is derived, never authored.** The model writes prose to a word
budget; every timing is computed:

```python
SECONDS_PER_IMAGE = 2.5

def shot_count(narration: str) -> int:
    words = len(narration.split())
    sentences = count_sentences(narration)
    seconds = (
        words / config.NARRATION_WORDS_PER_SECOND
        + sentences * config.NARRATION_SENTENCE_PAUSE_SECONDS
    )
    return max(1, round(seconds / config.SECONDS_PER_IMAGE))
```

The sentence-pause term is not optional. A 40-word paragraph of two sentences
and one of five sentences differ by ~5 seconds of real runtime; word count
alone under-counts shots on choppy sections.

`count_sentences` counts runs of `.`, `!` or `?` (a run of consecutive
terminators counts once, so an ellipsis is one sentence end), and returns at
least 1 for any non-empty narration — narration written without terminal
punctuation still costs one pause.

**`start` and `end` are outputs.** They make the saved file read like the
target format, but nothing consumes them for generation. They are written twice:
estimated by the script stage, then overwritten with measured values by the
archive stage, which is the first point at which every section's audio is
known to exist. The model is never asked to declare a timecode.

**A shot is a string.** No `Shot` dataclass wrapping a single field. Promote it
if and when a shot needs a second attribute.

Config changes: `SECONDS_PER_IMAGE = 2.5` and `TARGET_VIDEO_SECONDS = 85`
arrive; `IMAGE_PROMPTS_PER_ITEM`, `SECONDS_PER_FRAME`, `TITLE_FONT_SIZE`,
`TITLE_LINE_SPACING`, `TITLE_SIDE_MARGIN`, `TITLE_GAP_BELOW_IMAGE` and
`TITLE_COLOR` leave. `NARRATION_WORDS_PER_SECOND` and
`NARRATION_SENTENCE_PAUSE_SECONDS` stay and become load-bearing in two more
places. The overridable-config list in `api/config_view.py` must be updated to
match.

Files become `section_01_shot_03.png`, `section_01.mp3`,
`composed_section_01_shot_03.png`.

### 2. Two AI calls

**Call 1 — the script writer.** In: topic, target seconds. Out: `title` and
`sections[{label, narration}]`, under a strict JSON schema. Labels are
free-form; the only structural constraints in the prompt are that the first
section hooks and the last one calls to action.

The word budget handed to it must account for the inter-sentence pause. The
naive figure for 85 seconds is `85 x 3.15 = 268` words, which at ~20 sentences
renders as roughly 118 seconds:

```python
def word_budget(target_seconds: float, avg_words_per_sentence: int = 13) -> int:
    seconds_per_sentence = (
        avg_words_per_sentence / config.NARRATION_WORDS_PER_SECOND
        + config.NARRATION_SENTENCE_PAUSE_SECONDS
    )
    return round(target_seconds / seconds_per_sentence * avg_words_per_sentence)
```

85 seconds budgets ~190 words.

The safety and copyright blocks carry over from today's `generate_list` prompt
unchanged. New voice guidance: second person, direct address, open on a
concrete surprising fact rather than a summary, and no meta narration ("in this
video we'll explore...").

**Call 2 — the image-prompt writer.** In: the full script — every label and
every narration — plus the shot count computed for each section. Out: `style`,
the global style sheet, and `sections[{label, prompts[]}]`.

Seeing the whole script at once is the point: it is what lets the model plan a
visual arc and author a style sheet that serves every section rather than the
first one.

Two constraints this call must be given explicitly:

**The first prompt of every section is self-contained.** Chaining resets at
each boundary, so shot 1 is generated from text alone and must establish the
entire scene. Shots 2..n are written as deltas — "the same wolf, now stepping
toward the firelight" — because they are generated as edits of the shot before
them. Prompts written without this knowledge produce sections whose opening
frame is an incoherent fragment.

**The style sheet is the only continuity carrier across a cut.** Within a
section the previous image holds the look. Across sections there is no image
reference at all, so the style text is the sole reason the wolf in the payoff
is the same wolf as in the hook.

**Count mismatches are tolerated, not corrected.** We computed the shot budget
ourselves, and assembly divides each section's measured audio by however many
prompts actually exist — a section returning 4 prompts against a budget of 5
still yields a correct video whose shots hold 3.1s instead of 2.5s. Strictness
would buy nothing and add a brittle retry loop. Validation is therefore: every
section present, at least one prompt each. A missing or empty section is the
only trigger for a repair call — exactly one, which re-sends call 2 naming the
offending sections. If the repair also comes back short, the stage fails rather
than generating a section with no visuals.

### 3. Stages and concurrency

Six stages replace five:

```
script -> prompts -> [review gate] -> media -> compose -> video -> archive
```

Prompt generation is its own stage rather than part of script generation, so
the progress UI can name what it is waiting on.

**The two-wave structure disappears.** Today's anchor/follow-up split exists
only because follow-up frames need an anchor that does not yet exist. With
chaining sequential *inside* a section, that ordering is internal to one job,
and a single `run_all` submits everything:

```
audio section 1..6          |
chain section 1 (2 shots)   |  all submitted at once,
chain section 2 (5 shots)   |  MAX_CONCURRENT_REQUESTS workers
chain section 3 (8 shots)   |
...                         |
```

Parallelism is bounded by section count rather than image count, so wall time
is roughly the longest single chain — an 8-shot section at ~18s per edit is
about 2.5 minutes, against 8-11 for a single global chain.

**Progress reporting.** `run_all` fires `on_done` once per job, so a chain job
would tick the progress bar once per section — a regression against the current
per-image asset list. The chain job therefore takes an `on_shot` callback,
records a `TaskResult` per shot as it goes, and returns that list; the stage
flattens the lists into the results it reports. `run_all`'s contract is
untouched and `describe_failures` still operates on the flattened list.

**Mid-chain failure.** If shot 3 exhausts its retries, shots 4+ have no
reference to continue from. The chain tracks the last shot that *succeeded* and
continues from that; if none has, the next shot is generated fresh from text.
A single failure then costs one frame and one continuity beat rather than the
section's entire tail.

**Compose stage.** Keeps the blurred 1080x1920 backdrop composition, drops the
title text entirely, and centres the image vertically instead of seating it
above a reserved title band.

Module renames follow the stage names, keeping the existing directory layout:
`scripts/ai/generate_list/` becomes `scripts/ai/generate_script/`, a new
`scripts/ai/generate_prompts/` holds call 2, and
`scripts/non_ai/create_titled_images_short/` becomes
`scripts/non_ai/compose_frames/`. `pipeline.TOTAL_STAGES` goes from 5 to 6.

### 4. Assembly

`build_section_clip` mirrors today's `build_item_clip`. `segment_bounds` is
reused unchanged — it already accepts an `int` meaning "that many equal
segments", which is exactly the even split this design needs. `beat_weights` is
deleted.

**Silence belongs only at the two ends.** `INTRO_SILENCE_SECONDS` and
`OUTRO_SILENCE_SECONDS` are applied per item today; carried over unchanged that
would put 4.2 seconds of dead air inside a continuous video, audible as a
hiccup at every section boundary. The intro silence applies to the first
section only, the outro to the last, and interior boundaries butt directly
together.

The per-section durations measured here are the same ones the archive stage
writes back into `script.json` as `start` and `end`, replacing the estimates.
Assembly returns them alongside the video path so nothing reopens the audio
twice.

### 5. Wire contract and review gate

`api/schemas.py` and `frontend/src/lib/types.ts` change together, as the
former's docstring requires.

| Today | New |
|---|---|
| `num_items` | `target_seconds` (15-180) |
| `ItemPayload{title, description, style, beats[], image_prompts[]}` | `ScriptPayload{title, style, sections[]}` and `SectionPayload{label, narration, prompts[]}` |
| `ApproveItemsRequest` | `ApproveScriptRequest` |
| status `generating_list` | `generating_script`, then `generating_prompts` |

`Run.items` becomes `Run.script`. `STAGE_SEQUENCE` in the frontend gains the
prompts stage. `ItemEditor` becomes `ScriptEditor`: a global style textarea,
then each section as a label field, a narration textarea, and its prompt rows
with add and remove.

**Editing narration does not recount shots.** The prompts already exist paired
one-to-one with shots, so a recount would either orphan prompts or require
generating new ones — an AI call in the middle of a review gate. It would also
make the edit box feel booby-trapped, with rows appearing and disappearing
during typing. And it is unnecessary: assembly measures the rendered audio and
divides by the actual shot count, so an edited narration stays exactly in sync
and only shifts how long each shot holds. A reviewer wanting a different rhythm
adds or deletes a prompt row directly.

### 6. Existing archives

`generated_data/*/list_items.json` holds the old shape. Rather than a migration
script, the archive reader attempts the new shape and, on failure, marks that
archive `legacy` and exposes only its slug, video and media counts. Nothing
already generated disappears from the browser, and no parsing code for the dead
format survives in the pipeline.

## Testing

Test modules mirror source modules 1:1, as the suite already does:
`test_generate_script.py`, `test_generate_prompts.py`, `test_compose.py`.

The cases that must be written first, because they are where this design can
quietly be wrong:

- `word_budget` and `shot_count` arithmetic, table-driven, including the
  sentence-pause term. A version that ignores pauses passes a naive test and
  produces videos 40% over target.
- Mid-chain failure falling back to the last successful shot, and to a
  from-text generation when no shot has yet succeeded.
- `segment_bounds` even split across a section's shots.
- Silence appearing only at the first and last section of the concatenation.
- Call 2 validation honouring an off-budget prompt count rather than retrying.
- Archive reader marking an old-shape directory `legacy` without raising.

## Out of scope

- Burned-in narration captions.
- Background music.
- Any mode that produces the old list format.
- Forced alignment of narration to audio; per-section measurement is
  sufficient for the sync this design needs.
