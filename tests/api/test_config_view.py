import base64
from types import SimpleNamespace

import pytest

import config
from api.config_view import (
    OVERRIDABLE,
    ConfigOverrideError,
    apply_overrides,
    effective_config,
    run_overrides,
    validate_overrides,
)
from scripts.ai.generate_images.utils import generate_image


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


def test_effective_config_leaves_out_the_production_preset():
    # The config page renders every value as a scalar.
    assert "PRODUCTION_IMAGE_SETTINGS" not in effective_config()


def test_run_overrides_are_untouched_without_production_models():
    assert run_overrides({"MAX_RETRIES": 2}, False) == {"MAX_RETRIES": 2}


def test_run_overrides_add_the_production_preset():
    assert run_overrides({"MAX_RETRIES": 2}, True) == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "high",
        "MAX_RETRIES": 2,
    }


def test_an_explicit_override_beats_the_production_preset():
    assert run_overrides({"IMAGE_QUALITY": "low"}, True) == {
        "IMAGE_MODEL": "gpt-image-2",
        "IMAGE_QUALITY": "low",
    }


def test_run_overrides_do_not_mutate_their_input_or_the_preset():
    given = {"IMAGE_QUALITY": "low"}
    run_overrides(given, True)
    assert given == {"IMAGE_QUALITY": "low"}
    assert config.PRODUCTION_IMAGE_SETTINGS["IMAGE_QUALITY"] == "high"


def test_the_production_preset_beats_an_image_model_pinned_by_the_environment(
    monkeypatch,
):
    monkeypatch.setattr(config, "IMAGE_MODEL", "some-pinned-model")
    with apply_overrides(run_overrides({}, True)):
        assert config.IMAGE_MODEL == "gpt-image-2"
    assert config.IMAGE_MODEL == "some-pinned-model"


def test_the_production_preset_reaches_the_image_api(tmp_path):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        encoded = base64.b64encode(b"png-bytes").decode()
        return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])

    client = SimpleNamespace(images=SimpleNamespace(generate=generate))
    square = config.IMAGE_SIZE

    with apply_overrides(run_overrides({}, True)):
        generate_image("a dodo", tmp_path / "dodo.png", client=client)

    assert calls[0]["model"] == "gpt-image-2"
    assert calls[0]["quality"] == "high"
    assert calls[0]["size"] == square
