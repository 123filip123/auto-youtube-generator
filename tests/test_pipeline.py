from pathlib import Path

import pytest

import pipeline
from models import Script, Section
from utils.openai_support import TaskResult


def build_script(prompts_per_section=(2, 3)):
    return Script(
        topic="wolves",
        title="T",
        style="A grey-blue wolf.",
        sections=tuple(
            Section(f"S{i}", f"Narration {i}.", tuple(f"p{j}" for j in range(n)))
            for i, n in enumerate(prompts_per_section, start=1)
        ),
    )


def test_total_stages_is_six():
    assert pipeline.TOTAL_STAGES == 6


def test_media_job_total_counts_one_audio_per_section_plus_every_shot():
    assert pipeline.media_job_total(build_script((2, 3))) == 2 + 5


def test_compose_job_total_counts_every_shot():
    assert pipeline.compose_job_total(build_script((2, 3))) == 5


def test_missing_media_lists_absent_audio_and_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    missing = pipeline.missing_media(build_script((2,)))
    assert len(missing) == 3  # one audio + two shots
    assert all(isinstance(path, Path) for path in missing)


def test_missing_media_ignores_empty_files_as_unusable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from utils.paths import ensure_output_dirs, section_audio_path

    ensure_output_dirs()
    section_audio_path(1).write_bytes(b"")
    assert section_audio_path(1) in pipeline.missing_media(build_script((1,)))


def test_asset_reporter_skips_the_chain_wrapper_result():
    """Chain jobs report per shot via on_shot; the wrapper must not re-report."""
    seen = []
    report = pipeline._asset_reporter(seen.append)
    report(TaskResult("images section 1", value=[TaskResult("shot 1")]))
    report(TaskResult("audio section 1", value=Path("a.mp3")))
    assert [result.label for result in seen] == ["audio section 1"]


def test_asset_reporter_passes_a_failed_chain_job_through():
    seen = []
    report = pipeline._asset_reporter(seen.append)
    report(TaskResult("images section 1", error=RuntimeError("pool died")))
    assert [result.label for result in seen] == ["images section 1"]


def test_asset_reporter_is_none_when_no_callback_given():
    assert pipeline._asset_reporter(None) is None


def test_sections_without_shots_names_the_offenders():
    script = Script(
        topic="t",
        title="T",
        sections=(
            Section("HOOK", "Narration.", ("p1",)),
            Section("SETUP", "Narration.", ()),
            Section("PAYOFF", "Narration.", ()),
        ),
    )
    assert pipeline.sections_without_shots(script) == ["2. SETUP", "3. PAYOFF"]


def test_sections_without_shots_is_empty_when_every_section_has_one():
    assert pipeline.sections_without_shots(build_script((1, 1))) == []


def test_media_stage_refuses_a_section_with_no_drawings(tmp_path, monkeypatch):
    """The review gate lets a human delete every drawing; fail before paying."""
    monkeypatch.chdir(tmp_path)
    script = Script(
        topic="t",
        title="T",
        sections=(Section("HOOK", "Narration.", ()),),
    )
    with pytest.raises(pipeline.PipelineError, match="no drawings"):
        pipeline.generate_media_stage(script, log=lambda _: None)


def test_fail_names_every_missing_file():
    with pytest.raises(pipeline.PipelineError, match="2 required file"):
        pipeline._fail("Media generation", [Path("a.png"), Path("b.mp3")])
