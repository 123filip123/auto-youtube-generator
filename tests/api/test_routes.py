from fastapi.testclient import TestClient

from api.app import create_app
from models import Script, Section, save_script
from utils.paths import ARCHIVED_SCRIPT_FILENAME


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_lists_values_and_overridable_fields(client):
    payload = client.get("/api/config").json()
    assert payload["values"]["VIDEO_WIDTH"] == 1080
    names = [field["name"] for field in payload["overridable"]]
    assert "IMAGE_QUALITY" in names
    quality = next(f for f in payload["overridable"] if f["name"] == "IMAGE_QUALITY")
    assert quality["choices"] == ["low", "medium", "high"]


def test_config_no_longer_offers_image_prompts_per_item(client):
    names = [field["name"] for field in client.get("/api/config").json()["overridable"]]
    assert "IMAGE_PROMPTS_PER_ITEM" not in names
    assert "TARGET_VIDEO_SECONDS" in names


def test_creating_a_run_returns_it(client):
    response = client.post("/api/runs", json={"topic": "wolves", "target_seconds": 85})
    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "wolves"
    assert body["id"]


def test_create_run_takes_target_seconds(client):
    response = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": False},
    )
    assert response.status_code == 201
    assert response.json()["target_seconds"] == 85


def test_create_run_rejects_a_target_below_fifteen(client):
    response = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 5}
    )
    assert response.status_code == 422


def test_create_run_rejects_a_target_above_one_eighty(client):
    response = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 200}
    )
    assert response.status_code == 422


def test_creating_a_run_rejects_a_blank_topic(client):
    response = client.post(
        "/api/runs", json={"topic": "   ", "target_seconds": 85}
    )
    assert response.status_code == 422


def test_creating_a_run_rejects_a_bad_override(client):
    response = client.post(
        "/api/runs",
        json={
            "topic": "wolves",
            "target_seconds": 85,
            "overrides": {"VIDEO_WIDTH": 720},
        },
    )
    assert response.status_code == 400
    assert "not overridable" in response.json()["detail"]


def test_a_second_run_conflicts(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    second = client.post(
        "/api/runs", json={"topic": "foxes", "target_seconds": 85}
    )
    assert second.status_code == 409


def test_getting_an_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_run_detail_exposes_the_script(client):
    created = client.post(
        "/api/runs", json={"topic": "wolves", "target_seconds": 85}
    ).json()
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert "script" in detail
    assert set(detail["script"]) == {"topic", "title", "style", "sections"}


def test_approving_script_resumes_the_run(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/script",
        json={
            "script": {
                "topic": "wolves",
                "title": "Wolves Domesticated Themselves",
                "style": "A grey-blue wolf with amber eyes.",
                "sections": [
                    {"label": "HOOK", "narration": "An edited hook.", "prompts": ["x"]}
                ],
            }
        },
    )
    assert response.status_code == 200

    store.wait_for_idle()
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert detail["status"] == "completed"
    assert detail["script"]["sections"][0]["narration"] == "An edited hook."
    assert detail["video_url"].startswith("/media/outputs/video_output/")


def test_approve_script_accepts_an_edited_script(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    detail = client.get(f"/api/runs/{created['id']}").json()

    script = detail["script"]
    script["sections"][0]["narration"] = "An edited hook."
    script["sections"][0]["prompts"] = ["one prompt only"]

    response = client.post(f"/api/runs/{created['id']}/script", json={"script": script})
    assert response.status_code == 200
    approved = response.json()["script"]
    assert approved["sections"][0]["narration"] == "An edited hook."
    assert approved["sections"][0]["prompts"] == ["one prompt only"]


def test_approve_script_rejects_a_script_with_no_sections(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    response = client.post(
        f"/api/runs/{created['id']}/script",
        json={"script": {"topic": "w", "title": "T", "style": "", "sections": []}},
    )
    assert response.status_code == 400


def test_approve_script_discards_client_supplied_timings(client, store):
    """`start`/`end` are output-only: a client can send anything, but the

    server re-derives them from the narration rather than storing them.
    """
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    script = client.get(f"/api/runs/{created['id']}").json()["script"]

    for section in script["sections"]:
        section["start"] = 999.0
        section["end"] = 999.0

    approved = client.post(
        f"/api/runs/{created['id']}/script", json={"script": script}
    ).json()["script"]
    for section in approved["sections"]:
        assert section["start"] != 999.0
        assert section["end"] != 999.0

    # And the re-derived timings are what `run_detail` keeps reporting too,
    # not just what the approve response happened to echo back.
    detail_sections = client.get(f"/api/runs/{created['id']}").json()["script"][
        "sections"
    ]
    for section in detail_sections:
        assert section["start"] != 999.0
        assert section["end"] != 999.0


def test_editing_narration_does_not_recount_prompts(client, store):
    """The review gate never regenerates prompts; the shot list is the user's."""
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")
    script = client.get(f"/api/runs/{created['id']}").json()["script"]

    before = len(script["sections"][0]["prompts"])
    script["sections"][0]["narration"] = "A much much much longer narration. " * 10
    approved = client.post(
        f"/api/runs/{created['id']}/script", json={"script": script}
    ).json()["script"]
    assert len(approved["sections"][0]["prompts"]) == before


def test_cancelling_a_run(client, store):
    created = client.post(
        "/api/runs",
        json={"topic": "wolves", "target_seconds": 85, "review_script": True},
    ).json()
    store.wait_for_status(created["id"], "awaiting_review")

    assert client.post(f"/api/runs/{created['id']}/cancel").status_code == 200
    store.wait_for_idle()
    assert client.get(f"/api/runs/{created['id']}").json()["status"] == "cancelled"


def test_archives_are_listed_and_readable(client, tmp_path):
    folder = tmp_path / "generated_data" / "birds"
    (folder / "images").mkdir(parents=True)
    save_script(
        Script(
            topic="birds",
            title="Birds",
            sections=(Section("HOOK", "A bird.", ("a",)),),
        ),
        folder / ARCHIVED_SCRIPT_FILENAME,
    )
    (folder / "images" / "section_01_shot_01.png").write_bytes(b"x")

    listing = client.get("/api/archives").json()
    assert [entry["slug"] for entry in listing] == ["birds"]

    detail = client.get("/api/archives/birds").json()
    assert detail["title"] == "Birds"
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
