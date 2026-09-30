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


def test_storyboard_style_allows_recognisable_features():
    module = importlib.reload(config)
    style = module.STORYBOARD_STYLE.lower()
    assert "hair" in style
    # A featureless round head cannot resemble anyone in particular.
    assert "minimal interior detail" not in style


def test_default_tier_is_draft():
    module = importlib.reload(config)
    assert module.MODEL_TIER == "draft"
    assert module.TEXT_MODEL == "gpt-4.1-mini"
    assert module.TEXT_TEMPERATURE == pytest.approx(0.7)
    assert module.IMAGE_MODEL == "gpt-image-1"
    assert module.IMAGE_SIZE == "1024x1024"
    assert module.IMAGE_QUALITY == "medium"


def test_quality_tier_selects_the_premium_models(monkeypatch):
    module = reload_config(monkeypatch, MODEL_TIER="quality")
    assert module.TEXT_MODEL == "gpt-5.5"
    assert module.IMAGE_MODEL == "gpt-image-2"
    assert module.IMAGE_QUALITY == "high"


def test_quality_tier_draws_portrait_images(monkeypatch):
    # A square image fills barely half a 1080x1920 frame; portrait fills it.
    module = reload_config(monkeypatch, MODEL_TIER="quality")
    assert module.IMAGE_SIZE == "1024x1536"


def test_quality_tier_leaves_the_temperature_unset(monkeypatch):
    # GPT-5 models reject every temperature but their own default.
    module = reload_config(monkeypatch, MODEL_TIER="quality")
    assert module.TEXT_TEMPERATURE is None


def test_tts_is_the_same_on_both_tiers(monkeypatch):
    # gpt-4o-mini-tts is the only speech model that honours `instructions`,
    # so there is no higher tier to move up to.
    draft = importlib.reload(config).TTS_MODEL
    assert reload_config(monkeypatch, MODEL_TIER="quality").TTS_MODEL == draft


def test_an_explicit_env_var_beats_the_tier(monkeypatch):
    module = reload_config(monkeypatch, MODEL_TIER="quality", IMAGE_QUALITY="low")
    assert module.IMAGE_QUALITY == "low"
    assert module.IMAGE_MODEL == "gpt-image-2"


def test_an_unknown_tier_raises(monkeypatch):
    with pytest.raises(ValueError, match="MODEL_TIER"):
        reload_config(monkeypatch, MODEL_TIER="cheap")
