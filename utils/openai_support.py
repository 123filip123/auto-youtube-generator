"""Shared retry policy and bounded parallelism for OpenAI calls.

Two things live here because every stage needs both:

1. A retry policy that backs off on transient failures (rate limits, timeouts,
   5xx) but fails immediately on `BadRequestError` — a prompt rejected by the
   content filter will never succeed on retry, so retrying just wastes time.
2. A helper that submits jobs into a shared, capped thread pool and returns
   results in submission order with per-job errors captured rather than raised.
"""

from concurrent.futures import Executor
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

import config

RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


def _wait_strategy():
    return wait_exponential_jitter(
        initial=config.RETRY_INITIAL_WAIT_SECONDS,
        max=config.RETRY_MAX_WAIT_SECONDS,
    )


def with_retry(fn: Callable) -> Callable:
    """Retry `fn` on transient OpenAI failures with exponential backoff."""
    return retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(config.MAX_RETRIES),
        wait=_wait_strategy(),
        reraise=True,
    )(fn)


@dataclass
class TaskResult:
    """The outcome of one parallel job: either a value or the error it raised."""

    label: str
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


Job = tuple[str, Callable[[], Any]]


def run_all(executor: Executor, jobs: Sequence[Job]) -> list[TaskResult]:
    """Run every job on `executor`, returning results in submission order.

    A failing job does not stop the others; its exception is captured on the
    corresponding `TaskResult`. Passing a shared executor lets several stages
    interleave their work under one global concurrency cap.
    """
    submitted = [(label, executor.submit(fn)) for label, fn in jobs]

    results: list[TaskResult] = []
    for label, future in submitted:
        try:
            results.append(TaskResult(label, value=future.result()))
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            results.append(TaskResult(label, error=exc))
    return results


def describe_failures(results: Sequence[TaskResult]) -> str:
    """Render a human-readable summary of failures, or "" if there were none."""
    failures = [r for r in results if not r.ok]
    if not failures:
        return ""
    lines = [f"  - {r.label}: {type(r.error).__name__}: {r.error}" for r in failures]
    return f"{len(failures)} job(s) failed:\n" + "\n".join(lines)
