import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Item
from scripts.ai.generate_images.generate_images import generate_images, image_jobs
from scripts.ai.generate_images.utils import generate_image
from utils.openai_support import run_all

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeImages:
    def __init__(self, b64=None, error=None):
        self.b64 = b64
        self.error = error
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])


def fake_client(b64=None, error=None):
    images = FakeImages(b64=b64, error=error)
    return SimpleNamespace(images=images), images


def two_items():
    return [
        Item("A", "First.", ("a1", "a2", "a3")),
        Item("B", "Second.", ("b1", "b2", "b3")),
    ]


def test_generate_image_writes_the_decoded_bytes(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    destination = tmp_path / "out.png"
    result = generate_image("a dodo", destination, client=client)
    assert result == destination
    assert destination.read_bytes() == PNG_BYTES


def test_generate_image_creates_parent_directories(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    destination = tmp_path / "deep" / "nested" / "out.png"
    generate_image("a dodo", destination, client=client)
    assert destination.exists()


def test_generate_image_passes_configured_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr("config.IMAGE_MODEL", "test-image-model")
    monkeypatch.setattr("config.IMAGE_QUALITY", "high")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    generate_image("a dodo", tmp_path / "out.png", client=client)
    assert images.calls[0]["model"] == "test-image-model"
    assert images.calls[0]["quality"] == "high"
    assert images.calls[0]["prompt"] == "a dodo"
    assert images.calls[0]["n"] == 1


def test_generate_image_raises_when_no_data_returned(tmp_path):
    client, _ = fake_client(b64=None)
    with pytest.raises(ValueError, match="No image data"):
        generate_image("a dodo", tmp_path / "out.png", client=client)


def test_generate_image_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(b64=None)
    destination = tmp_path / "out.png"
    with pytest.raises(ValueError):
        generate_image("a dodo", destination, client=client)
    assert not destination.exists()


def test_image_jobs_fans_out_one_job_per_prompt():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    jobs = image_jobs(two_items(), client=client)
    assert len(jobs) == 6


def test_image_jobs_labels_identify_item_and_prompt():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    labels = [label for label, _ in image_jobs(two_items(), client=client)]
    assert labels[0] == "image item 1 prompt 1"
    assert labels[-1] == "image item 2 prompt 3"


def test_image_jobs_are_not_executed_when_built():
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    image_jobs(two_items(), client=client)
    assert images.calls == []


def test_generate_images_writes_every_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    results = generate_images(two_items(), client=client)
    assert all(r.ok for r in results)
    assert Path("outputs/image_output/item_01_prompt_01.png").exists()
    assert Path("outputs/image_output/item_02_prompt_03.png").exists()


def test_generate_images_reports_failures_without_stopping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    original = images.generate
    calls = {"n": 0}

    def sometimes_fail(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("content filtered")
        return original(**kwargs)

    images.generate = sometimes_fail
    results = generate_images(two_items(), client=client)
    assert sum(1 for r in results if not r.ok) == 1
    assert sum(1 for r in results if r.ok) == 5


def test_jobs_run_correctly_through_the_shared_runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, image_jobs(two_items(), client=client))
    assert all(r.ok for r in results)


try:  # openai >= 3 vendors httpx2; older releases use httpx.
    import httpx2 as httpx
except ImportError:  # pragma: no cover - depends on the installed openai
    import httpx

import openai


def bad_request(code):
    request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
    response = httpx.Response(400, request=request)
    body = {"message": "rejected", "type": "image_generation_user_error", "code": code}
    return openai.BadRequestError("rejected", response=response, body=body)


class FakeChat:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class ScriptedImages:
    """Raise or succeed in the order given, one outcome per call."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(data=[SimpleNamespace(b64_json=outcome)])


def scripted_client(outcomes, rewrite="a rewritten prompt"):
    images = ScriptedImages(outcomes)
    chat = FakeChat(rewrite)
    client = SimpleNamespace(
        images=images, chat=SimpleNamespace(completions=chat)
    )
    return client, images, chat


GOOD_B64 = base64.b64encode(PNG_BYTES).decode()


def test_a_moderation_block_retries_once_with_a_rewritten_prompt(tmp_path):
    client, images, _ = scripted_client(
        [bad_request("moderation_blocked"), GOOD_B64], rewrite="a neon dance floor"
    )
    destination = tmp_path / "out.png"
    generate_image("an iconic album cover", destination, client=client)
    assert [c["prompt"] for c in images.calls] == [
        "an iconic album cover",
        "a neon dance floor",
    ]
    assert destination.read_bytes() == PNG_BYTES


def test_the_rewrite_request_shows_the_model_the_blocked_prompt(tmp_path):
    client, _, chat = scripted_client([bad_request("moderation_blocked"), GOOD_B64])
    generate_image("an iconic album cover", tmp_path / "out.png", client=client)
    sent = " ".join(m["content"] for m in chat.calls[0]["messages"])
    assert "an iconic album cover" in sent


def test_a_second_moderation_block_raises_without_a_third_try(tmp_path):
    client, images, _ = scripted_client(
        [bad_request("moderation_blocked"), bad_request("moderation_blocked")]
    )
    with pytest.raises(openai.BadRequestError):
        generate_image("an iconic album cover", tmp_path / "out.png", client=client)
    assert len(images.calls) == 2


def test_other_bad_requests_are_not_rewritten(tmp_path):
    client, images, chat = scripted_client([bad_request("invalid_size")])
    with pytest.raises(openai.BadRequestError):
        generate_image("a dodo", tmp_path / "out.png", client=client)
    assert len(images.calls) == 1
    assert chat.calls == []


def test_a_failed_image_job_removes_the_previous_runs_file(tmp_path, monkeypatch):
    # outputs/ is reused between runs; a stale picture must not stand in for
    # an image this run failed to make.
    monkeypatch.chdir(tmp_path)
    stale = Path("outputs/image_output/item_01_prompt_01.png")
    stale.parent.mkdir(parents=True)
    stale.write_bytes(PNG_BYTES)
    client, _ = fake_client(error=RuntimeError("boom"))
    (_, job), *_ = image_jobs(two_items(), client=client)
    with pytest.raises(RuntimeError):
        job()
    assert not stale.exists()
