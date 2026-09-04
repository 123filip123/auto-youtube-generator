import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Beat, Item
from scripts.ai.generate_images.generate_images import (
    anchor_jobs,
    followup_jobs,
    generate_images,
)
from scripts.ai.generate_images.utils import (
    generate_image,
    generate_image_from_reference,
    styled_prompt,
)

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
        Item(
            "A",
            "First.",
            (Beat("n1", "a1"), Beat("n2", "a2"), Beat("n3", "a3")),
            "STYLE A.",
        ),
        Item(
            "B",
            "Second.",
            (Beat("n4", "b1"), Beat("n5", "b2"), Beat("n6", "b3")),
            "STYLE B.",
        ),
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


def test_anchor_jobs_is_one_per_item():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    jobs = anchor_jobs(two_items(), client=client)
    assert [label for label, _ in jobs] == [
        "image item 1 beat 1",
        "image item 2 beat 1",
    ]


def test_followup_jobs_covers_every_later_beat():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    labels = [label for label, _ in followup_jobs(two_items(), client=client)]
    assert labels == [
        "image item 1 beat 2",
        "image item 1 beat 3",
        "image item 2 beat 2",
        "image item 2 beat 3",
    ]


def test_followup_jobs_is_empty_for_single_beat_items():
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    items = [Item("A", "First.", (Beat("n", "a1"),), "STYLE A.")]
    assert followup_jobs(items, client=client) == []


def test_jobs_are_not_executed_when_built():
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    anchor_jobs(two_items(), client=client)
    followup_jobs(two_items(), client=client)
    assert images.calls == []
    assert images.edits == []


def test_anchor_prompts_carry_the_global_and_item_style(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    assert images.calls[0]["prompt"] == "GLOBAL. STYLE A. a1"
    assert images.calls[1]["prompt"] == "GLOBAL. STYLE B. b1"


def test_followup_prompts_carry_the_global_and_item_style(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("config.STORYBOARD_STYLE", "GLOBAL.")
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    for _, run in followup_jobs(two_items(), client=client):
        run()
    assert images.edits[0]["prompt"] == "GLOBAL. STYLE A. a2"
    assert images.edits[-1]["prompt"] == "GLOBAL. STYLE B. b3"


def test_followups_read_their_own_items_anchor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    for _, run in anchor_jobs(two_items(), client=client):
        run()
    label, run = followup_jobs(two_items(), client=client)[2]  # item 2 beat 2
    run()
    assert label == "image item 2 beat 2"
    assert Path("outputs/image_output/item_02_prompt_02.png").exists()


def test_generate_images_writes_every_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client, _ = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    results = generate_images(two_items(), client=client)
    assert all(r.ok for r in results)
    assert len(results) == 6
    assert Path("outputs/image_output/item_01_prompt_01.png").exists()
    assert Path("outputs/image_output/item_02_prompt_03.png").exists()


def test_a_failed_anchor_fails_its_followups_rather_than_vanishing(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    client, images = fake_client(b64=base64.b64encode(PNG_BYTES).decode())
    original = images.generate

    def fail_item_one(**kwargs):
        if kwargs["prompt"].endswith("a1"):
            raise RuntimeError("content filtered")
        return original(**kwargs)

    images.generate = fail_item_one
    results = generate_images(two_items(), client=client)

    failed = {r.label: r for r in results if not r.ok}
    assert set(failed) == {
        "image item 1 beat 1",
        "image item 1 beat 2",
        "image item 1 beat 3",
    }
    assert isinstance(failed["image item 1 beat 2"].error, FileNotFoundError)
