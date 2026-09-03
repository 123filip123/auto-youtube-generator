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
        assert isinstance(value, (str, int, float)), f"{name} is {type(value)}"


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
