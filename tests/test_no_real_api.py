"""The suite must never be able to spend money.

Run workers execute on background threads. If one outlives the test that
stubbed its stages, it falls through to the real pipeline — so the key it
would find there has to be a dummy.
"""

import os

from utils.open_ai_client import get_open_ai_client


def test_the_suite_never_holds_a_real_api_key():
    assert os.environ.get("OPENAI_API_KEY") == "test-key-not-real"


def test_the_shared_client_is_built_from_the_dummy_key():
    assert get_open_ai_client().api_key == "test-key-not-real"
