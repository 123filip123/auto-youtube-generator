import pytest

from api.runs import RunConflictError, RunNotFoundError, RunStore
from models import Script, Section
from tests.api.conftest import one_script


def test_a_run_without_review_completes(tmp_path, monkeypatch, stub_stages):
    monkeypatch.chdir(tmp_path)

    store = RunStore()
    run = store.start("wolves", 85, review_script=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert finished.error is None
    assert [section.label for section in finished.script.sections] == [
        "HOOK",
        "SETUP",
    ]
    assert finished.archive_slug == "wolves"
    assert finished.finished_at is not None


def test_a_review_run_pauses_until_the_script_is_approved(
    tmp_path, monkeypatch, stub_stages
):
    monkeypatch.chdir(tmp_path)

    store = RunStore()
    run = store.start("wolves", 85, review_script=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    assert store.get(run.id).status == "awaiting_review"

    edited = Script(
        topic="wolves",
        title="Wolves, Edited",
        sections=(Section("HOOK", "An edited hook.", ("x", "y")),),
    )
    store.approve_script(run.id, edited)
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "completed"
    assert [section.label for section in finished.script.sections] == ["HOOK"]


def test_starting_a_second_run_while_one_is_active_conflicts(
    tmp_path, monkeypatch, stub_stages
):
    monkeypatch.chdir(tmp_path)

    store = RunStore()
    first = store.start("wolves", 85, review_script=True, overrides={})
    store.wait_for_status(first.id, "awaiting_review")

    with pytest.raises(RunConflictError):
        store.start("foxes", 85, review_script=False, overrides={})


def test_a_failing_stage_marks_the_run_failed(tmp_path, monkeypatch, stub_stages):
    from pipeline import PipelineError

    monkeypatch.chdir(tmp_path)

    def boom(script, client=None, log=print, on_asset=None):
        raise PipelineError("no images")

    monkeypatch.setattr("api.runs.pipeline.generate_media_stage", boom)

    store = RunStore()
    run = store.start("wolves", 85, review_script=False, overrides={})
    store.wait_for_idle()

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert "no images" in finished.error


def test_cancelling_while_awaiting_review_ends_the_run(
    tmp_path, monkeypatch, stub_stages
):
    monkeypatch.chdir(tmp_path)

    store = RunStore()
    run = store.start("wolves", 85, review_script=True, overrides={})
    store.wait_for_status(run.id, "awaiting_review")

    store.cancel(run.id)
    store.wait_for_idle()

    assert store.get(run.id).status == "cancelled"


def test_approving_a_run_that_is_not_awaiting_review_conflicts(
    tmp_path, monkeypatch, stub_stages
):
    monkeypatch.chdir(tmp_path)

    store = RunStore()
    run = store.start("wolves", 85, review_script=False, overrides={})
    store.wait_for_idle()

    with pytest.raises(RunConflictError):
        store.approve_script(run.id, one_script())


def test_get_raises_for_an_unknown_run():
    with pytest.raises(RunNotFoundError):
        RunStore().get("nope")


def test_overrides_apply_only_while_the_run_executes(
    tmp_path, monkeypatch, stub_stages
):
    import config

    monkeypatch.chdir(tmp_path)
    original = config.IMAGE_QUALITY
    seen = []

    def record(topic, target_seconds, client=None, log=print):
        seen.append(config.IMAGE_QUALITY)
        return one_script()

    monkeypatch.setattr("api.runs.pipeline.generate_script_stage", record)

    store = RunStore()
    store.start(
        "wolves", 85, review_script=False, overrides={"IMAGE_QUALITY": "low"}
    )
    store.wait_for_idle()

    assert seen == ["low"]
    assert config.IMAGE_QUALITY == original
