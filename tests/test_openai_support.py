import threading
import time
from concurrent.futures import ThreadPoolExecutor

import openai
import pytest

import config
from utils.openai_support import (
    RETRYABLE_EXCEPTIONS,
    TaskResult,
    describe_failures,
    run_all,
    temperature_kwargs,
    with_retry,
)

try:  # openai >= 3 vendors httpx2; older releases use httpx.
    import httpx2 as httpx
except ImportError:  # pragma: no cover - depends on the installed openai
    import httpx


def make_api_error(cls, status_code):
    request = httpx.Request("POST", "https://api.openai.com/v1/x")
    response = httpx.Response(status_code, request=request)
    return cls("boom", response=response, body=None)


def test_rate_limit_is_retryable():
    assert openai.RateLimitError in RETRYABLE_EXCEPTIONS


def test_internal_server_error_is_retryable():
    assert openai.InternalServerError in RETRYABLE_EXCEPTIONS


def test_bad_request_is_not_retryable():
    # A content-policy rejection will never succeed on retry.
    assert openai.BadRequestError not in RETRYABLE_EXCEPTIONS


def test_with_retry_recovers_from_a_transient_error(monkeypatch):
    monkeypatch.setattr("utils.openai_support._wait_strategy", lambda: (lambda rs: 0))
    calls = []

    @with_retry
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise make_api_error(openai.RateLimitError, 429)
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_with_retry_gives_up_on_a_non_retryable_error(monkeypatch):
    monkeypatch.setattr("utils.openai_support._wait_strategy", lambda: (lambda rs: 0))
    calls = []

    @with_retry
    def rejected():
        calls.append(1)
        raise make_api_error(openai.BadRequestError, 400)

    with pytest.raises(openai.BadRequestError):
        rejected()
    assert len(calls) == 1, "a content-policy rejection must not be retried"


def test_run_all_preserves_input_order():
    jobs = [(f"job-{i}", (lambda i=i: i)) for i in range(10)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, jobs)
    assert [r.value for r in results] == list(range(10))
    assert [r.label for r in results] == [f"job-{i}" for i in range(10)]


def test_run_all_collects_errors_without_stopping():
    def explode():
        raise RuntimeError("nope")

    jobs = [("good", lambda: 1), ("bad", explode), ("also-good", lambda: 3)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = run_all(executor, jobs)

    assert [r.ok for r in results] == [True, False, True]
    assert isinstance(results[1].error, RuntimeError)
    assert results[0].value == 1
    assert results[2].value == 3


def test_run_all_actually_runs_in_parallel():
    barrier = threading.Barrier(4, timeout=5)

    def wait_for_others():
        barrier.wait()
        return True

    jobs = [(f"j{i}", wait_for_others) for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = run_all(executor, jobs)

    # The barrier only releases if all four ran concurrently.
    assert all(r.ok for r in results)


def test_run_all_respects_the_worker_cap():
    live = 0
    peak = 0
    lock = threading.Lock()

    def track():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1

    jobs = [(f"j{i}", track) for i in range(12)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        run_all(executor, jobs)

    assert peak <= 3


def test_run_all_handles_an_empty_job_list():
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert run_all(executor, []) == []


def test_describe_failures_lists_each_failure():
    results = [
        TaskResult("image item 1 prompt 2", error=RuntimeError("filtered")),
        TaskResult("audio item 3", value="ok"),
        TaskResult("image item 4 prompt 1", error=ValueError("empty")),
    ]
    message = describe_failures(results)
    assert "image item 1 prompt 2" in message
    assert "filtered" in message
    assert "image item 4 prompt 1" in message
    assert "audio item 3" not in message


def test_describe_failures_is_empty_when_all_succeeded():
    assert describe_failures([TaskResult("a", value=1)]) == ""


def test_run_all_reports_each_result_as_it_finishes():
    seen = []
    jobs = [("a", lambda: 1), ("b", lambda: 2), ("c", lambda: 3)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = run_all(executor, jobs, on_done=seen.append)

    assert [r.label for r in results] == ["a", "b", "c"]
    assert sorted(r.label for r in seen) == ["a", "b", "c"]


def test_run_all_reports_failures_to_the_callback():
    def boom():
        raise ValueError("nope")

    seen = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        run_all(executor, [("bad", boom)], on_done=seen.append)

    assert len(seen) == 1
    assert not seen[0].ok
    assert isinstance(seen[0].error, ValueError)


def test_temperature_kwargs_carries_the_configured_temperature(monkeypatch):
    monkeypatch.setattr(config, "TEXT_TEMPERATURE", 0.4)
    assert temperature_kwargs() == {"temperature": 0.4}


def test_temperature_kwargs_is_empty_when_the_model_refuses_one(monkeypatch):
    # A GPT-5 model 400s on any temperature but its own default, so the
    # argument has to be absent rather than set to the default.
    monkeypatch.setattr(config, "TEXT_TEMPERATURE", None)
    assert temperature_kwargs() == {}
