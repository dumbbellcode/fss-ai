#!/usr/bin/env python3
"""Retry helpers for LLM calls against transient provider errors.

OpenRouter routes a model to one or more upstream providers; those providers can
return transient ``429``/``5xx`` errors (e.g. a shared-pool rate limit). A failed
call would otherwise abort a long batch run, so wrap invocations with
:func:`invoke_with_retry` to back off and try again.
"""

import time
from collections.abc import Callable
from typing import Any

import openai

# ``langchain_openai`` re-raises openai errors behind its own subclasses but sets
# the original openai exception as ``__cause__``, so the chain is inspected too.
_RETRYABLE_OPENAI_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


def is_retryable_llm_error(exc: BaseException) -> bool:
    """Return True when ``exc`` (or its cause chain) is a transient LLM error."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _RETRYABLE_OPENAI_ERRORS):
            return True
        status = getattr(current, "status_code", None)
        if isinstance(status, int) and (status == 429 or 500 <= status < 600):
            return True
        current = current.__cause__ or current.__context__
    return False


def invoke_with_retry(
    runnable: Any,
    messages: Any,
    *,
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> Any:
    """Invoke ``runnable`` on ``messages``, retrying transient errors with backoff.

    ``max_retries`` is the number of retries *after* the first attempt. Non-transient
    errors (e.g. auth or bad-request) are raised immediately without retrying.
    """
    attempt = 0
    while True:
        try:
            return runnable.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - re-raised unless transient
            attempt += 1
            if attempt > max_retries or not is_retryable_llm_error(exc):
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep(delay)
