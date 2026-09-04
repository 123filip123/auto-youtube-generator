import importlib

import pytest

import config


def reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


def test_defaults_are_sane():
    module = importlib.reload(config)
    assert module.TARGET_VIDEO_SECONDS == 85
    assert module.SECONDS_PER_IMAGE == pytest.approx(2.5)
    assert module.NARRATION_WORDS_PER_SECOND == pytest.approx(3.15)
    assert module.NARRATION_SENTENCE_PAUSE_SECONDS == pytest.approx(1.6)
    assert module.MAX_CONCURRENT_REQUESTS == 4
    assert module.VIDEO_WIDTH == 1080
    assert module.VIDEO_HEIGHT == 1920
    assert module.VIDEO_FPS == 24


def test_int_env_override(monkeypatch):
    module = reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="9")
    assert module.MAX_CONCURRENT_REQUESTS == 9


def test_str_env_override(monkeypatch):
    module = reload_config(monkeypatch, TEXT_MODEL="my-model")
    assert module.TEXT_MODEL == "my-model"


def test_blank_env_falls_back_to_default(monkeypatch):
    module = reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="   ")
    assert module.MAX_CONCURRENT_REQUESTS == 4


def test_non_numeric_env_raises(monkeypatch):
    with pytest.raises(ValueError, match="MAX_CONCURRENT_REQUESTS"):
        reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="four")


def test_non_positive_env_raises(monkeypatch):
    with pytest.raises(ValueError, match="MAX_CONCURRENT_REQUESTS"):
        reload_config(monkeypatch, MAX_CONCURRENT_REQUESTS="0")


@pytest.fixture(autouse=True)
def restore_config():
    yield
    importlib.reload(config)
