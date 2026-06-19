import pytest

from orchestrator.retry import (
    BACKOFF_MAX_S,
    MAX_TRANSIENT_RETRIES,
    backoff_delay,
    is_transient_sdk_error,
)


@pytest.mark.parametrize(
    "msg",
    [
        "API Error: 529 Overloaded",
        "anthropic overloaded_error",
        "429 Too Many Requests",
        "Rate limit exceeded",
        "503 Service Unavailable",
        "Connection reset by peer",
        "Request timed out",
        "ECONNRESET",
    ],
)
def test_transient_errors_are_retryable(msg):
    assert is_transient_sdk_error(RuntimeError(msg))


@pytest.mark.parametrize(
    "msg",
    [
        "KeyError: 'foo'",
        "ValidationError: bad schema",
        "401 Unauthorized",
        "permission denied",
        "No such file or directory",
    ],
)
def test_non_transient_errors_fail_fast(msg):
    assert not is_transient_sdk_error(RuntimeError(msg))


def test_backoff_is_monotonic_and_capped():
    delays = [backoff_delay(n) for n in range(1, MAX_TRANSIENT_RETRIES + 1)]
    assert delays == sorted(delays)
    assert all(d <= BACKOFF_MAX_S for d in delays)
    assert delays[0] < delays[-1]


def test_backoff_handles_floor():
    assert backoff_delay(0) == backoff_delay(1)
