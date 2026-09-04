"""One whole run driven through the HTTP API, with no network calls.

This is the automated stand-in for driving the UI by hand: it exercises the
real stages — real image/audio generation calls (faked at the OpenAI client),
real frame composition, a real moviepy encode, real archiving — behind the
same endpoints the frontend calls. Only the OpenAI client is faked.
"""

import base64
import io
import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import config
from api.app import create_app
from utils.paths import (
    composed_image_path,
    section_audio_path,
    section_image_path,
    video_output_path,
)

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


def _png_b64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 90, 140)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _silent_mp3() -> bytes:
    """One second of silence, via the ffmpeg that ships with imageio-ffmpeg."""
    import imageio_ffmpeg

    completed = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "1", "-f", "mp3", "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    return completed.stdout


class FakeOpenAI:
    """Answers the calls the pipeline makes, with usable payloads.

    `chat.completions.create` answers the script then the prompts, in that
    order, for every run: each run makes exactly two chat calls (one per
    script/prompts stage), so odd calls are the script and even calls are the
    prompts regardless of how many runs share this client.
    """

    def __init__(self, audio: bytes) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._chat),
        )
        self.images = SimpleNamespace(generate=self._image, edit=self._edit)
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self._speech))
        self._audio = audio
        self._chat_calls = 0
        self.edits = []

    def _chat(self, **_kwargs):
        self._chat_calls += 1
        content = SCRIPT_JSON if self._chat_calls % 2 == 1 else PROMPTS_JSON
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def _image(self, **_kwargs):
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64())])

    def _edit(self, **kwargs):
        """Every shot after a section's first continues its anchor frame."""
        self.edits.append(kwargs["image"][0].read())
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64())])

    def _speech(self, **_kwargs):
        payload = self._audio
        return SimpleNamespace(iter_bytes=lambda: iter([payload]))


@pytest.mark.slow
def test_a_whole_run_through_the_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A small, fast encode. These are not per-run overridable, so patch them.
    monkeypatch.setattr(config, "VIDEO_WIDTH", 216)
    monkeypatch.setattr(config, "VIDEO_HEIGHT", 384)
    monkeypatch.setattr(config, "VIDEO_FPS", 6)

    client = FakeOpenAI(_silent_mp3())

    with TestClient(create_app(client=client)) as http:
        store = http.app.state.run_store

        created = http.post(
            "/api/runs",
            json={
                "topic": "Top Wolf Facts",
                # The floor, to keep the render tiny.
                "target_seconds": 15,
                "review_script": True,
                # Exercised as a real per-run override.
                "overrides": {"IMAGE_QUALITY": "low"},
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        # 1. The run pauses for review with the generated, prompt-filled script.
        store.wait_for_status(run_id, "awaiting_review")
        paused = http.get(f"/api/runs/{run_id}").json()
        sections = paused["script"]["sections"]
        assert [section["label"] for section in sections] == ["HOOK", "PAYOFF"]
        assert sections[0]["prompts"] == ["a snarling wolf", "a goofy dog"]

        # 2. Edit the narration and drop the second section, the way the UI does.
        approved = http.post(
            f"/api/runs/{run_id}/script",
            json={
                "script": {
                    "topic": "Top Wolf Facts",
                    "title": "Wolves Chose Us",
                    "style": "A lean grey-blue wolf with amber eyes.",
                    "sections": [
                        {
                            "label": "HOOK",
                            "narration": (
                                "Your dog's ancestor could have killed you. "
                                "Wolves chose us as much as we chose them."
                            ),
                            "prompts": [
                                "a snarling wolf",
                                "a wolf and a person side by side",
                            ],
                        }
                    ],
                }
            },
        )
        assert approved.status_code == 200, approved.text

        # 3. The rest of the pipeline runs to completion.
        store.wait_for_idle(timeout=180)
        detail = http.get(f"/api/runs/{run_id}").json()
        assert detail["status"] == "completed", detail["error"]
        assert [s["label"] for s in detail["script"]["sections"]] == ["HOOK"]

        # The edited section asked for two prompts, so two images were generated.
        assert section_image_path(1, 1).stat().st_size > 0
        assert section_image_path(1, 2).stat().st_size > 0

        # The second shot went through the continuation call, referencing the
        # first shot rather than being drawn from its prompt alone.
        assert len(client.edits) == 1
        assert client.edits[0] == section_image_path(1, 1).read_bytes()
        assert section_audio_path(1).stat().st_size > 0
        assert composed_image_path(1, 1).stat().st_size > 0
        assert composed_image_path(1, 2).stat().st_size > 0
        assert video_output_path().stat().st_size > 0

        # 4. The video is served over the media mount.
        assert detail["video_url"].startswith(
            "/media/outputs/video_output/final_video_short.mp4?run="
        )
        assert http.get(detail["video_url"]).status_code == 200

        # 5. The archive is complete and readable through the API.
        assert detail["archive_slug"] == "top_wolf_facts"
        archive = http.get(f"/api/archives/{detail['archive_slug']}").json()
        assert archive["video_url"] is not None
        assert archive["title"] == "Wolves Chose Us"
        (archived_section,) = archive["sections"]
        assert archived_section["label"] == "HOOK"
        assert len(archived_section["image_urls"]) == 2
        assert len(archived_section["composed_image_urls"]) == 2
        assert archived_section["audio_url"] is not None
        for url in [archive["video_url"], *archived_section["image_urls"]]:
            assert http.get(url).status_code == 200, url

        # 6. The override was reverted once the run finished.
        assert config.IMAGE_QUALITY == "medium"

        # 7. A second run is allowed now that the first is terminal — the
        # only end-to-end proof that the single-run lock actually releases
        # after a genuine full pipeline run, not just a stubbed one.
        assert (
            http.post(
                "/api/runs", json={"topic": "Foxes", "target_seconds": 15}
            ).status_code
            == 201
        )
        store.wait_for_idle(timeout=180)
