import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Item
from scripts.ai.generate_images.generate_images import generate_images, image_jobs
from scripts.ai.generate_images.utils import (
    generate_image,
    generate_image_from_reference,
    styled_prompt,
)
from utils.openai_support import run_all

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeImages:
    def __init__(self, b64=None, error=None):
        self.b64 = b64
        self.error = error
        self.calls = []
        self.edits = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])

    def edit(self, **kwargs):
        # The handle is closed once the caller's `with` block exits, so read
        # it now and record the bytes rather than the file object.
        recorded = dict(kwargs)
        recorded["reference_bytes"] = kwargs["image"][0].read()
        self.edits.append(recorded)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.b64)])


def fake_client(b64=None, error=None):
    images = FakeImages(b64=b64, error=error)
    return SimpleNamespace(images=images), images


def two_items():
    return [
        Item.from_prompts("A", "First.", ("a1", "a2", "a3")),
        Item.from_prompts("B", "Second.", ("b1", "b2", "b3")),
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


def test_styled_prompt_orders_global_style_then_item_then_beat(monkeypatch):
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    assert styled_prompt("ITEM.", "BEAT.") == "GLOBAL. ITEM. BEAT."


def test_styled_prompt_skips_a_blank_item_style(monkeypatch):
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    assert styled_prompt("", "BEAT.") == "GLOBAL. BEAT."


def test_generate_from_reference_sends_the_reference_file(tmp_path):
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    destination = tmp_path / "follow_up.png"

    result = generate_image_from_reference(
        "beat two", reference, destination, client=client
    )

    assert result == destination
    assert destination.read_bytes() == PNG_BYTES
    assert images.calls == []  # it used edit, not generate
    assert len(images.edits) == 1
    assert images.edits[0]["prompt"] == "beat two"
    assert images.edits[0]["reference_bytes"] == PNG_BYTES


def test_generate_from_reference_passes_configured_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr("config.IMAGE_MODEL", "test-image-model")
    monkeypatch.setattr("config.IMAGE_QUALITY", "high")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    generate_image_from_reference(
        "beat two", reference, tmp_path / "out.png", client=client
    )
    assert images.edits[0]["model"] == "test-image-model"
    assert images.edits[0]["quality"] == "high"
    assert images.edits[0]["n"] == 1


def test_generate_from_reference_fails_loudly_without_an_anchor(tmp_path):
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    with pytest.raises(FileNotFoundError, match="anchor frame"):
        generate_image_from_reference(
            "beat two", tmp_path / "missing.png", tmp_path / "out.png", client=client
        )


def test_generate_from_reference_leaves_no_partial_file_on_failure(tmp_path):
    client, _ = fake_client(b64=None)
    reference = tmp_path / "anchor.png"
    reference.write_bytes(PNG_BYTES)
    destination = tmp_path / "out.png"
    with pytest.raises(ValueError, match="No image data"):
        generate_image_from_reference(
            "beat two", reference, destination, client=client
        )
    assert not destination.exists()
