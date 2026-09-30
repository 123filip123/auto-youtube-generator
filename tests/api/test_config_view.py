import json

import pytest

import config
from api.config_view import (
    OVERRIDABLE,
    ConfigOverrideError,
    apply_overrides,
    effective_config,
    validate_overrides,
)


def test_effective_config_exposes_uppercase_constants():
    values = effective_config()
    assert values["VIDEO_WIDTH"] == 1080
    assert values["IMAGE_QUALITY"] == config.IMAGE_QUALITY
    assert "os" not in values


def test_effective_config_values_are_json_safe():
    for name, value in effective_config().items():
        assert isinstance(value, (str, int, float, type(None))), (
            f"{name} is {type(value)}"
        )


def test_every_overridable_field_names_a_real_constant():
    for field in OVERRIDABLE:
        assert hasattr(config, field.name)


def test_validate_overrides_coerces_integers():
    assert validate_overrides({"MAX_RETRIES": "7"}) == {"MAX_RETRIES": 7}


def test_validate_overrides_rejects_an_unknown_name():
    with pytest.raises(ConfigOverrideError, match="not overridable"):
        validate_overrides({"VIDEO_WIDTH": 720})


def test_validate_overrides_rejects_a_non_positive_integer():
    with pytest.raises(ConfigOverrideError, match="greater than zero"):
        validate_overrides({"MAX_RETRIES": 0})


def test_validate_overrides_rejects_a_value_outside_the_choices():
    with pytest.raises(ConfigOverrideError, match="must be one of"):
        validate_overrides({"IMAGE_QUALITY": "ultra"})


def test_apply_overrides_restores_the_previous_values():
    original = config.IMAGE_QUALITY
    with apply_overrides({"IMAGE_QUALITY": "low"}):
        assert config.IMAGE_QUALITY == "low"
    assert config.IMAGE_QUALITY == original


def test_apply_overrides_restores_after_an_exception():
    original = config.MAX_RETRIES
    with pytest.raises(RuntimeError):
        with apply_overrides({"MAX_RETRIES": 1}):
            raise RuntimeError("boom")
    assert config.MAX_RETRIES == original


def test_storyboard_style_is_overridable():
    assert any(field.name == "STORYBOARD_STYLE" for field in OVERRIDABLE)
    assert validate_overrides({"STORYBOARD_STYLE": "  crayon doodles  "}) == {
        "STORYBOARD_STYLE": "crayon doodles"
    }


def test_model_tier_is_overridable():
    assert "MODEL_TIER" in [field.name for field in OVERRIDABLE]


def test_applying_the_quality_tier_swaps_every_model_it_covers():
    with apply_overrides({"MODEL_TIER": "quality"}):
        assert config.TEXT_MODEL == "gpt-5.5"
        assert config.IMAGE_MODEL == "gpt-image-2"
        assert config.IMAGE_SIZE == "1024x1536"
        assert config.IMAGE_QUALITY == "high"
        assert config.TEXT_TEMPERATURE is None
    assert config.TEXT_MODEL == "gpt-4.1-mini"
    assert config.TEXT_TEMPERATURE == pytest.approx(0.7)


def test_an_explicit_field_beats_the_tier_it_arrives_with():
    with apply_overrides({"MODEL_TIER": "quality", "IMAGE_QUALITY": "low"}):
        assert config.IMAGE_QUALITY == "low"
        assert config.IMAGE_MODEL == "gpt-image-2"


def test_validate_overrides_rejects_an_unknown_tier():
    with pytest.raises(ConfigOverrideError):
        validate_overrides({"MODEL_TIER": "cheap"})


def test_effective_config_survives_an_unset_temperature(monkeypatch):
    # The quality tier leaves TEXT_TEMPERATURE unset; null is still JSON-safe.
    monkeypatch.setattr(config, "TEXT_TEMPERATURE", None)
    json.dumps(effective_config())
