# Auto YouTube Generator

## Overview

This project automatically generates YouTube Shorts-style videos based on a topic you provide. It uses OpenAI APIs to write a narrated script broken into labelled sections, draw the sequence of simple line drawings that illustrates it, and assemble them into a vertical video suitable for YouTube Shorts.

**Pipeline steps:**

1. Generate a validated script via JSON-schema structured outputs: a title, a
   style sheet naming the recurring figure and its colours, and a sequence of
   labelled sections, each pairing narration with the drawing prompts that
   illustrate it. Section and shot counts fall out of narration length, not a
   fixed knob — see `utils/timing.py`. Note that the voice leaves roughly
   `NARRATION_SENTENCE_PAUSE_SECONDS` of silence after each sentence, which
   puts a floor under how short a shot's hold time can be.
2. Design the drawing prompts for every section's shots.
3. Generate every section's narration and shots, capped at
   `MAX_CONCURRENT_REQUESTS` concurrent API calls: shots within a section are
   drawn as a chain, each continuing the one before so the figure stays
   recognisable, while different sections run in parallel and narration rides
   alongside. Verify every expected asset exists before continuing.
4. Compose each shot onto a blurred 1080x1920 backdrop.
5. Assemble the composed frames and narration into a vertical video, holding
   each frame still for as long as the narration it illustrates.
6. Archive the run — script, audio, images, composed frames and the finished
   video — into `generated_data/<topic-slug>/`.

---

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/123filip123/auto-youtube-generator.git
   cd auto-youtube-generator
   ```

2. **Create a virtual environment (optional but recommended):**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   For Windows (also make sure you have Python set up in Path):

   ```bash
   python -m venv venv
   .\venv\Scripts\Activate
   ```

3. **Install dependencies:**

   ```bash
   pip install --upgrade setuptools wheel (do this for windows if you have issues)
   pip install -r requirements.txt
   ```

---

## OpenAI API Key Setup

This app requires access to the OpenAI API for text, image, and audio generation. You must set your API key as an environment variable.

1. **Create a `.env` file in the project root:**

   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   ```

2. **Alternatively, export the variable in your shell:**
   ```bash
   export OPENAI_API_KEY=your_openai_api_key_here
   ```

---

## Configuration

Every tunable lives in `config.py` and can be overridden with an environment
variable of the same name (see `.env.example`). The ones worth knowing:

| Variable | Default | What it does |
|---|---|---|
| `MAX_CONCURRENT_REQUESTS` | `4` | Parallel OpenAI calls. Lower it if you hit rate limits. |
| `MAX_RETRIES` | `5` | Attempts per call before giving up. Rate limits and 5xx are retried with exponential backoff; content-policy rejections are not. |
| `TEXT_MODEL` | `gpt-4.1-mini` | Generates the script. Must support JSON schema structured outputs. |
| `TTS_MODEL` | `gpt-4o-mini-tts` | Narration. Must support the `instructions` parameter. |
| `TTS_VOICE` | `ash` | Narration voice. |
| `IMAGE_MODEL` | `gpt-image-1` | Image generation. |
| `IMAGE_QUALITY` | `medium` | `low` is cheaper and faster; `high` is slower and costs more. |
| `TARGET_VIDEO_SECONDS` | `85` | How long the finished script should run. |
| `STORYBOARD_STYLE` | flat-colour stick-figure line art | The drawing style every frame shares. |
| `VIDEO_PRESET` | `medium` | x264 preset. `ultrafast` renders quicker at a larger file size. |

---

## How to Run the App

### Run the Pipeline

Interactively:

```bash
python main.py
```

Or non-interactively:

```bash
python main.py --topic "Top 5 Extinct Animals" --seconds 60
```

Output lands in `outputs/`, and a complete copy of the run is archived to
`generated_data/<topic-slug>/`.

### Run the Web UI

The web UI is two processes: the FastAPI backend and the Vite dev server.

**Terminal 1 — backend (must be started from the repository root):**

```bash
uvicorn api.app:app --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install   # first time only
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` and `/media` to the
backend, so there is nothing else to configure.

The UI can:

- start a run and watch it stage by stage, with per-asset success and failure
- pause after the script and its drawing prompts are generated so you can edit
  the narration and drawings before any images or narration are paid for
- override any of the tunables listed under [Configuration](#configuration) for
  a single run, without editing `.env`
- browse every archived run in `generated_data/` with its images, narration and
  video

**Only one run can be active at a time.** `outputs/` is a single shared
workspace with fixed filenames, so starting a second run while one is in flight
returns a conflict. Cancelling stops the run at the next stage boundary; work
already in flight — an OpenAI batch or a video render — finishes first.

Run history lives in memory. Restarting the backend clears it —
`generated_data/` is the durable record.

To serve the UI from the backend alone (no Vite process), build it first; the
backend serves `frontend/dist/` at `/` when that directory exists:

```bash
cd frontend && npm run build
```

---

## Output

- Generated data (JSON, images, audio, video) will be saved in the `outputs/` and `generated_data/` directories.
- The final video will be in `outputs/video_output/`.

---

## Requirements

- Python 3.10+
- OpenAI API key
- [ffmpeg](https://ffmpeg.org/) (required by moviepy; install via `brew install ffmpeg` on macOS or your OS package manager)

---

## Notes

- Make sure your OpenAI account has access to the models listed under
  [Configuration](#configuration) (text, TTS, and image generation).
- If you hit rate limits, lower `MAX_CONCURRENT_REQUESTS`. Transient failures are
  already retried automatically with exponential backoff.
- For best results, use a topic that is suitable for list-style videos (e.g., "Amazing Space Facts").

## Demo Video

Watch a sample video generated by this tool: [Top 5 Most Delicious Sandwiches](https://www.youtube.com/shorts/s9-JNQis_JI?feature=share)

---

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

Frontend tests:

```bash
cd frontend
npm test        # vitest
npm run build   # type-check and build
```

Note that `moviepy` is pinned to `1.0.3` and requires `decorator==4.4.2`.
Upgrading either will break video assembly.
