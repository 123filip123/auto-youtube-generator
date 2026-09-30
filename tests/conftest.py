import pytest

import utils.open_ai_client

DUMMY_API_KEY = "test-key-not-real"


@pytest.fixture(autouse=True)
def no_real_api_key():
    """Make a real, paid OpenAI call impossible from inside the suite.

    Every test injects a fake client, but a run worker is a background thread:
    one that outlives its test's stubs would fall through to the real
    pipeline. With a dummy key and no cached client, the worst that can do is
    fail to authenticate.

    This patches through its own context rather than the `monkeypatch`
    fixture: requesting that fixture here would set it up before every other
    fixture, and so undo a test's environment changes after fixtures that
    rely on them already being gone.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("OPENAI_API_KEY", DUMMY_API_KEY)
        patch.setattr(utils.open_ai_client, "_client", None)
        yield
