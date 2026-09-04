"""One whole run driven through the HTTP API, with no network calls.

This is the automated stand-in for driving the UI by hand: it exercises the
real stages — Pillow titled-image rendering, a real moviepy encode, real
archiving — behind the same endpoints the frontend calls. Only the OpenAI
client is faked.
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
from utils.paths import audio_path, image_path, titled_image_path, video_output_path

ITEMS_JSON = json.dumps(
    {
        "items": [
            {
                "title": "Dodo",
                "description": "A flightless bird. It is extinct.",
                "image_prompts": ["a dodo"],
            },
            {
                "title": "Moa",
                "description": "A tall flightless bird. Also extinct.",
                "image_prompts": ["a moa"],
            },
        ]
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
    """Answers the three calls the pipeline makes, with usable payloads."""

    def __init__(self, audio: bytes) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._chat),
        )
        self.images = SimpleNamespace(generate=self._image, edit=self._edit)
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self._speech))
        self._audio = audio
        self.edits = []

    def _chat(self, **_kwargs):
        message = SimpleNamespace(content=ITEMS_JSON)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def _image(self, **_kwargs):
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64())])

    def _edit(self, **kwargs):
        """Every frame after the first continues the item's anchor frame."""
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
    monkeypatch.setattr(config, "TITLE_FONT_SIZE", 24)
    monkeypatch.setattr(config, "TITLE_GAP_BELOW_IMAGE", 40)

    client = FakeOpenAI(_silent_mp3())

    with TestClient(create_app(client=client)) as http:
        store = http.app.state.run_store

        created = http.post(
            "/api/runs",
            json={
                "topic": "Top 2 Extinct Birds",
                "num_items": 2,
                "review_items": True,
                # Exercised as a real per-run override.
                "overrides": {"IMAGE_PROMPTS_PER_ITEM": 1, "IMAGE_QUALITY": "low"},
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        # 1. The run pauses for review with both generated items.
        store.wait_for_status(run_id, "awaiting_review")
        paused = http.get(f"/api/runs/{run_id}").json()
        assert [item["title"] for item in paused["items"]] == ["Dodo", "Moa"]

        # 2. Edit a title and drop the second item, the way the UI does.
        approved = http.post(
            f"/api/runs/{run_id}/items",
            json={
                "items": [
                    {
                        "title": "Great Auk",
                        "description": "A flightless seabird. It is extinct.",
                        "image_prompts": ["a great auk", "a great auk in a hat"],
                    }
                ]
            },
        )
        assert approved.status_code == 200, approved.text

        # 3. The rest of the pipeline runs to completion.
        store.wait_for_idle(timeout=180)
        detail = http.get(f"/api/runs/{run_id}").json()
        assert detail["status"] == "completed", detail["error"]
        assert [item["title"] for item in detail["items"]] == ["Great Auk"]

        # The edited item asked for two prompts, so two images were generated
        # even though the run was started with IMAGE_PROMPTS_PER_ITEM=1.
        assert image_path(1, 1).stat().st_size > 0
        assert image_path(1, 2).stat().st_size > 0

        # The second frame went through the follow-up wave, referencing the
        # anchor frame rather than being drawn from its prompt alone.
        assert len(client.edits) == 1
        assert client.edits[0] == image_path(1, 1).read_bytes()
        assert audio_path(1).stat().st_size > 0
        assert titled_image_path(1, 1).stat().st_size > 0
        assert titled_image_path(1, 2).stat().st_size > 0
        assert video_output_path().stat().st_size > 0

        # 4. The video is served over the media mount.
        assert detail["video_url"].startswith(
            "/media/outputs/video_output/final_video_short.mp4?run="
        )
        assert http.get(detail["video_url"]).status_code == 200

        # 5. The archive is complete and readable through the API.
        assert detail["archive_slug"] == "top_2_extinct_birds"
        archive = http.get(f"/api/archives/{detail['archive_slug']}").json()
        assert archive["video_url"] is not None
        (archived_item,) = archive["items"]
        assert archived_item["title"] == "Great Auk"
        assert len(archived_item["image_urls"]) == 2
        assert len(archived_item["titled_image_urls"]) == 2
        assert archived_item["audio_url"] is not None
        for url in [archive["video_url"], *archived_item["image_urls"]]:
            assert http.get(url).status_code == 200, url

        # 6. The override was reverted once the run finished.
        assert config.IMAGE_QUALITY == "medium"

        # 7. A second run is allowed now that the first is terminal.
        assert (
            http.post("/api/runs", json={"topic": "Fish", "num_items": 1}).status_code
            == 201
        )
        store.wait_for_idle(timeout=180)
