import importlib

import pytest

import config


def reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


def test_defaults_are_sane():
    module = importlib.reload(config)
    assert module.IMAGE_PROMPTS_PER_ITEM == 3
    assert module.MAX_CONCURRENT_REQUESTS == 4
    assert module.VIDEO_WIDTH == 1080
    assert module.VIDEO_HEIGHT == 1920
    assert module.VIDEO_FPS == 24
    assert module.ZOOM_END_SCALE == pytest.approx(1.2)


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


def test_default_image_models_are_the_cheap_ones():
    module = importlib.reload(config)
    assert module.IMAGE_MODEL == "gpt-image-1"
    assert module.IMAGE_SIZE == "1024x1024"
    assert module.IMAGE_QUALITY == "medium"


def test_production_image_settings_select_the_better_model():
    assert config.PRODUCTION_IMAGE_SETTINGS == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "high",
    }


def test_production_image_settings_name_real_constants():
    for name in config.PRODUCTION_IMAGE_SETTINGS:
        assert hasattr(config, name)


def test_production_image_settings_keep_the_image_square():
    # The title is drawn beneath the image; a portrait image pushes it off
    # the bottom of the 1920px frame.
    assert "IMAGE_SIZE" not in config.PRODUCTION_IMAGE_SETTINGS
