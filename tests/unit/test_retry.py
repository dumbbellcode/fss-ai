from unittest.mock import Mock

import httpx
import openai
import pytest

from pre_processing.retry import invoke_with_retry, is_retryable_llm_error


def _rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError("rate limited upstream", response=response, body=None)


class _Status(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_is_retryable_for_openai_rate_limit():
    assert is_retryable_llm_error(_rate_limit_error())


def test_is_retryable_through_wrapped_cause():
    wrapper = RuntimeError("provider returned error")
    wrapper.__cause__ = _rate_limit_error()
    assert is_retryable_llm_error(wrapper)


def test_is_retryable_for_server_error_status():
    assert is_retryable_llm_error(_Status(503))


def test_is_not_retryable_for_client_error():
    assert not is_retryable_llm_error(_Status(400))
    assert not is_retryable_llm_error(ValueError("nope"))


def test_invoke_with_retry_returns_first_success():
    runnable = Mock()
    runnable.invoke.return_value = "ok"
    sleeps: list[float] = []

    result = invoke_with_retry(runnable, ["m"], sleep=sleeps.append)

    assert result == "ok"
    assert runnable.invoke.call_count == 1
    assert sleeps == []


def test_invoke_with_retry_retries_then_succeeds():
    runnable = Mock()
    runnable.invoke.side_effect = [_rate_limit_error(), "ok"]
    sleeps: list[float] = []

    result = invoke_with_retry(runnable, ["m"], base_delay=2.0, sleep=sleeps.append)

    assert result == "ok"
    assert runnable.invoke.call_count == 2
    assert sleeps == [2.0]


def test_invoke_with_retry_backs_off_exponentially():
    runnable = Mock()
    runnable.invoke.side_effect = [_Status(500), _Status(500), "ok"]
    sleeps: list[float] = []

    invoke_with_retry(runnable, ["m"], base_delay=1.0, sleep=sleeps.append)

    assert sleeps == [1.0, 2.0]


def test_invoke_with_retry_raises_after_max_retries():
    runnable = Mock()
    runnable.invoke.side_effect = _Status(429)
    sleeps: list[float] = []

    with pytest.raises(_Status):
        invoke_with_retry(runnable, ["m"], max_retries=2, sleep=sleeps.append)

    assert runnable.invoke.call_count == 3
    assert len(sleeps) == 2


def test_invoke_with_retry_does_not_retry_non_transient():
    runnable = Mock()
    runnable.invoke.side_effect = ValueError("bad request")
    sleeps: list[float] = []

    with pytest.raises(ValueError):
        invoke_with_retry(runnable, ["m"], sleep=sleeps.append)

    assert runnable.invoke.call_count == 1
    assert sleeps == []


def test_on_retry_callback_receives_attempt_and_delay():
    runnable = Mock()
    runnable.invoke.side_effect = [_rate_limit_error(), "ok"]
    events: list[tuple[int, float]] = []

    invoke_with_retry(
        runnable,
        ["m"],
        sleep=lambda _: None,
        on_retry=lambda attempt, delay, exc: events.append((attempt, delay)),
    )

    assert events == [(1, 2.0)]
