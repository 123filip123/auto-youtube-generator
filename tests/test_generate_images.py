import base64
from types import SimpleNamespace

import pytest

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


from models import Script, Section
from scripts.ai.generate_images import generate_images as images_module
from scripts.ai.generate_images.generate_images import (
    flatten_chain_results,
    run_section_chain,
    section_chain_jobs,
)
from utils.openai_support import TaskResult
from utils.paths import section_image_path


class RecordingImages:
    """Stands in for the two image entry points, recording every call."""

    def __init__(self, fail_on=()):
        self.fresh = []          # prompts generated from text alone
        self.continued = []      # (prompt, reference) pairs
        self.fail_on = set(fail_on)  # 1-based shot numbers that raise
        self._shot = 0

    def generate_image(self, prompt, destination, *, client=None):
        self._shot += 1
        if self._shot in self.fail_on:
            raise RuntimeError(f"shot {self._shot} failed")
        self.fresh.append(prompt)
        return destination

    def generate_image_from_reference(self, prompt, reference, destination, *, client=None):
        self._shot += 1
        if self._shot in self.fail_on:
            raise RuntimeError(f"shot {self._shot} failed")
        self.continued.append((prompt, reference))
        return destination


def install(monkeypatch, recorder):
    monkeypatch.setattr(images_module, "generate_image", recorder.generate_image)
    monkeypatch.setattr(
        images_module,
        "generate_image_from_reference",
        recorder.generate_image_from_reference,
    )


def build_section(prompts=("p1", "p2", "p3")):
    return Section("HOOK", "Narration.", tuple(prompts))


def test_first_shot_is_generated_from_text_alone(monkeypatch):
    recorder = RecordingImages()
    install(monkeypatch, recorder)
    run_section_chain(1, build_section(), "STYLE SHEET")
    assert len(recorder.fresh) == 1
    assert "STYLE SHEET" in recorder.fresh[0]
    assert "p1" in recorder.fresh[0]


def test_later_shots_continue_the_previous_shot(monkeypatch):
    recorder = RecordingImages()
    install(monkeypatch, recorder)
    run_section_chain(1, build_section(), "STYLE SHEET")
    assert len(recorder.continued) == 2
    assert recorder.continued[0][1] == section_image_path(1, 1)
    assert recorder.continued[1][1] == section_image_path(1, 2)


def test_a_mid_chain_failure_continues_from_the_last_success(monkeypatch):
    recorder = RecordingImages(fail_on={2})
    install(monkeypatch, recorder)
    results = run_section_chain(1, build_section(), "STYLE")
    assert [r.ok for r in results] == [True, False, True]
    # Shot 3 continues from shot 1, not from the missing shot 2.
    assert recorder.continued[-1][1] == section_image_path(1, 1)


def test_a_failed_first_shot_makes_the_next_shot_fresh(monkeypatch):
    recorder = RecordingImages(fail_on={1})
    install(monkeypatch, recorder)
    results = run_section_chain(1, build_section(), "STYLE")
    assert results[0].ok is False
    # Nothing has succeeded yet, so shot 2 is generated from text.
    assert len(recorder.fresh) == 1
    assert "p2" in recorder.fresh[0]


def test_reports_one_result_per_shot_with_a_readable_label(monkeypatch):
    install(monkeypatch, RecordingImages())
    results = run_section_chain(2, build_section(), "STYLE")
    assert [r.label for r in results] == [
        "image section 2 shot 1",
        "image section 2 shot 2",
        "image section 2 shot 3",
    ]


def test_on_shot_fires_once_per_shot_as_it_completes(monkeypatch):
    install(monkeypatch, RecordingImages())
    seen = []
    run_section_chain(1, build_section(), "STYLE", on_shot=seen.append)
    assert len(seen) == 3
    assert all(isinstance(entry, TaskResult) for entry in seen)


def test_one_job_per_section_with_prompts():
    script = Script(
        topic="t",
        title="T",
        style="STYLE",
        sections=(build_section(), Section("SETUP", "N.", ()), build_section(("a",))),
    )
    jobs = section_chain_jobs(script)
    # The promptless middle section contributes no job.
    assert [label for label, _ in jobs] == ["images section 1", "images section 3"]


def test_flatten_unwraps_per_section_result_lists():
    inner = [TaskResult("shot 1"), TaskResult("shot 2")]
    outer = [TaskResult("images section 1", value=inner)]
    assert flatten_chain_results(outer) == inner


def test_flatten_keeps_a_failed_chain_job_as_one_result():
    failed = TaskResult("images section 1", error=RuntimeError("pool died"))
    assert flatten_chain_results([failed]) == [failed]
