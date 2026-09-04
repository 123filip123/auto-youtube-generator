from pathlib import Path

import pytest

from api.runs import RunConflictError, RunNotFoundError, RunStore
from models import Item


def one_item():
    return [Item.from_prompts("Dodo", "A bird.", ("a", "b", "c"))]


def stub_stages(monkeypatch, *, items=None):
    """Replace every pipeline stage with a fast, side-effect-free fake."""
    produced = items if items is not None else one_item()

    monkeypatch.setattr(
        "api.runs.pipeline.generate_items_stage",
        lambda topic, num_items, client=None, log=print: produced,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.generate_media_stage",
        lambda items, client=None, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_titled_images_stage",
        lambda items, log=print, on_asset=None: None,
    )
    monkeypatch.setattr(
        "api.runs.pipeline.render_video_stage",
        lambda items, log=print: Path("outputs/video_output/final_video_short.mp4"),
    )
    monkeypatch.setattr(
        "api.runs.pipeline.archive_stage",
        lambda topic, items, log=print: Path("generated_data/birds"),
    )


def test_a_run_without_review_completes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert finished.error is None
    assert [item.title for item in finished.items] == ["Dodo"]
    assert finished.archive_slug == "birds"
    assert finished.finished_at is not None


def test_a_review_run_pauses_until_items_are_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    assert store.get(run.id).status == "awaiting_review"

    edited = [Item.from_prompts("Moa", "A taller bird.", ("x", "y"))]
    store.approve_items(run.id, edited)
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert [item.title for item in finished.items] == ["Moa"]


def test_starting_a_second_run_while_one_is_active_conflicts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    first = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(first.id, "awaiting_review")

    with pytest.raises(RunConflictError):
        store.start("Fish", 1, review_items=False, overrides={})


def test_a_failing_stage_marks_the_run_failed(tmp_path, monkeypatch):
    from pipeline import PipelineError

    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    def boom(items, client=None, log=print, on_asset=None):
        raise PipelineError("no images")

    monkeypatch.setattr("api.runs.pipeline.generate_media_stage", boom)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert "no images" in finished.error


def test_cancelling_while_awaiting_review_ends_the_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    store.cancel(run.id)
    store.wait_for_idle()

    assert store.get(run.id).status == "cancelled"


def test_approving_a_run_that_is_not_awaiting_review_conflicts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_stages(monkeypatch)

    store = RunStore()
    run = store.start("Birds", 1, review_items=False, overrides={})
    store.wait_for_idle()

    with pytest.raises(RunConflictError):
        store.approve_items(run.id, one_item())


def test_get_raises_for_an_unknown_run():
    with pytest.raises(RunNotFoundError):
        RunStore().get("nope")


def test_overrides_apply_only_while_the_run_executes(tmp_path, monkeypatch):
    import config

    monkeypatch.chdir(tmp_path)
    original = config.IMAGE_QUALITY
    seen = []

    def record(topic, num_items, client=None, log=print):
        seen.append(config.IMAGE_QUALITY)
        return one_item()

    stub_stages(monkeypatch)
    monkeypatch.setattr("api.runs.pipeline.generate_items_stage", record)

    store = RunStore()
    store.start("Birds", 1, review_items=False, overrides={"IMAGE_QUALITY": "low"})
    store.wait_for_idle()

    assert seen == ["low"]
    assert config.IMAGE_QUALITY == original
