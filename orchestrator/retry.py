"""Transient-error classification + backoff for the Worker SDK loop (Wave 0).

A transient upstream blip (Anthropic 529 Overloaded, a rate-limit, a dropped
connection) used to mark an autonomous run `failed` on the spot, so any
multi-hour run during an Anthropic load event died and needed a manual
relaunch. We classify these and retry the leg with exponential backoff instead;
genuine errors (bad config, auth, a real bug) still fail fast.
"""

MAX_TRANSIENT_RETRIES = 5
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 60.0

_TRANSIENT_MARKERS = (
    "429",
    "502",
    "503",
    "504",
    "529",
    "overloaded",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "service unavailable",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection error",
    "connection aborted",
    "econnreset",
    "remote end closed",
)


def is_transient_sdk_error(exc: BaseException) -> bool:
    """True for upstream blips worth retrying (overload, rate-limit, network),
    False for errors that indicate a real problem (bad config, auth, a bug)."""
    haystack = f"{type(exc).__name__} {exc}".lower()
    return any(marker in haystack for marker in _TRANSIENT_MARKERS)


def backoff_delay(retry: int) -> float:
    """Exponential backoff in seconds for the Nth transient retry (1-based),
    capped at BACKOFF_MAX_S."""
    if retry < 1:
        retry = 1
    return min(BACKOFF_BASE_S * (2 ** (retry - 1)), BACKOFF_MAX_S)
