import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from models import Item


def one_item():
    return [Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))]


def stub_stages(monkeypatch):
    monkeypatch.setattr(
        "api.runs.pipeline.generate_items_stage",
        lambda topic, num_items, client=None, log=print: one_item(),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_media_stage",
        lambda items, client=None, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_titled_images_stage",
        lambda items, log=print, on_asset=None: None,
    )
    def fake_render(items, log=print):
        # A real file, because run_detail only advertises a video_url for a
        # video that actually exists on disk.
        video = Path("outputs/video_output/final_video_short.mp4")
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"video")
        return video

    monkeypatch.setattr("api.runs.pipeline.render_video_stage", fake_render)
    monkeypatch.setattr(
        "api.runs.pipeline.archive_stage",
        lambda topic, items, log=print: Path("generated_data/birds"),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_lists_values_and_overridable_fields(client):
    payload = client.get("/api/config").json()
    assert payload["values"]["VIDEO_WIDTH"] == 1080
    names = [field["name"] for field in payload["overridable"]]
    assert "IMAGE_QUALITY" in names
    quality = next(f for f in payload["overridable"] if f["name"] == "IMAGE_QUALITY")
    assert quality["choices"] == ["low", "medium", "high"]


def test_creating_a_run_returns_it(client, monkeypatch):
    stub_stages(monkeypatch)
    response = client.post("/api/runs", json={"topic": "Birds", "num_items": 1})
    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "Birds"
    assert body["id"]


def test_creating_a_run_rejects_a_blank_topic(client):
    response = client.post("/api/runs", json={"topic": "   ", "num_items": 1})
    assert response.status_code == 422


def test_creating_a_run_rejects_a_bad_override(client):
    response = client.post(
        "/api/runs",
        json={"topic": "Birds", "num_items": 1, "overrides": {"VIDEO_WIDTH": 720}},
    )
    assert response.status_code == 400
    assert "not overridable" in response.json()["detail"]


def test_a_second_run_conflicts(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    client.app.state.run_store.wait_for_status(created["id"], "awaiting_review")
    second = client.post("/api/runs", json={"topic": "Fish", "num_items": 1})
    assert second.status_code == 409


def test_getting_an_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_approving_items_resumes_the_run(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    store = client.app.state.run_store
    store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/items",
        json={
            "items": [{"title": "Moa", "description": "Taller.", "image_prompts": ["x"]}]
        },
    )
    assert response.status_code == 200

    store.wait_for_idle()
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert detail["status"] == "completed"
    assert detail["items"][0]["title"] == "Moa"
    assert detail["video_url"].startswith("/media/outputs/video_output/")


def test_approving_items_rejects_an_item_with_no_prompts(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    client.app.state.run_store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/items",
        json={"items": [{"title": "Moa", "description": "d", "image_prompts": []}]},
    )
    assert response.status_code == 400


def test_cancelling_a_run(client, monkeypatch):
    stub_stages(monkeypatch)
    created = client.post(
        "/api/runs", json={"topic": "Birds", "num_items": 1, "review_items": True}
    ).json()
    store = client.app.state.run_store
    store.wait_for_status(created["id"], "awaiting_review")

    assert client.post(f"/api/runs/{created['id']}/cancel").status_code == 200
    store.wait_for_idle()
    assert client.get(f"/api/runs/{created['id']}").json()["status"] == "cancelled"


def test_archives_are_listed_and_readable(client, tmp_path):
    folder = tmp_path / "generated_data" / "birds"
    (folder / "images").mkdir(parents=True)
    (folder / "list_items.json").write_text(
        json.dumps(
            {"items": [{"title": "Dodo", "description": "d", "image_prompts": ["a"]}]}
        )
    )
    (folder / "images" / "item_01_prompt_01.png").write_bytes(b"x")

    listing = client.get("/api/archives").json()
    assert [entry["slug"] for entry in listing] == ["birds"]

    detail = client.get("/api/archives/birds").json()
    assert detail["items"][0]["title"] == "Dodo"
    assert client.get("/api/archives/missing").status_code == 404


def test_a_built_frontend_is_served_with_an_spa_fallback(tmp_path, monkeypatch):
    # Client-side routes must survive a refresh or a pasted deep link, which
    # plain StaticFiles does not do — it 404s anything but an existing file.
    monkeypatch.chdir(tmp_path)
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>")
    (dist / "favicon.svg").write_text("<svg/>")

    with TestClient(create_app()) as http:
        assert http.get("/").status_code == 200
        for route in ("/archives", "/config", "/runs/abc123"):
            response = http.get(route)
            assert response.status_code == 200, route
            assert "id='root'" in response.text

        # Real files still win, and the API is untouched.
        assert http.get("/favicon.svg").text == "<svg/>"
        assert http.get("/api/health").json() == {"status": "ok"}
        assert http.get("/api/runs/nope").status_code == 404
