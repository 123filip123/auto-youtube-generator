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
