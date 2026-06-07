from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.state import IterationUsage


DENIED_BASH_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?:^|[;&|\n]\s*)rm\s+-[rRfF]*[rR][rRfF]*\b"),
        "rm -rf is denied",
    ),
    (re.compile(r"\bgit\s+push\s+(-f|--force)"), "force push is denied"),
    (re.compile(r"\bgit\s+reset\s+--hard"), "git reset --hard is denied"),
    (re.compile(r"\bnpm\s+publish\b"), "npm publish is denied"),
    (re.compile(r"\bpnpm\s+publish\b"), "pnpm publish is denied"),
    (
        re.compile(r"\binfisical\s+secrets\s+(set|delete)\b"),
        "infisical secret writes are denied",
    ),
    (
        re.compile(r"\binfisical\s+run\b"),
        "direct infisical run is denied: use the execute_with_secrets tool",
    ),
    (
        re.compile(r"\bcurl\b[^\n;&|]*\bhttps?://[^\s;&|]*\bapi\."),
        "outbound curl to api.* hosts is denied",
    ),
    (
        re.compile(r"\bgh\s+pr\s+(comment|merge|close|review)\b"),
        "gh pr write actions are denied",
    ),
    (
        re.compile(r"\bgh\s+issue\s+(comment|close)\b"),
        "gh issue write actions are denied",
    ),
    (
        re.compile(r"\bterraform\s+(apply|destroy)\b"),
        "terraform apply/destroy is denied",
    ),
    (
        re.compile(r"\bdrop\s+(table|database)\b", re.IGNORECASE),
        "destructive SQL is denied",
    ),
]


def bash_allowed(cmd: str) -> tuple[bool, str]:
    for pat, reason in DENIED_BASH_PATTERNS:
        if pat.search(cmd):
            return False, reason
    return True, ""


def iteration_cap_hit(*, iteration: int, max_iterations: int) -> bool:
    return iteration >= max_iterations


def wall_clock_cap_hit(*, started_at: float, max_seconds: float) -> bool:
    # wall-clock cap: time.time() is correct here, monotonic would not honor real-world hours
    return (time.time() - started_at) >= max_seconds


def kill_switch_active(switch_path: Path) -> bool:
    return switch_path.exists()


# Protective default USD ceiling auto-applied to api_key-mode runs when the
# operator gives no explicit --max-cost-usd. Subscription runs are uncapped (the
# per-token dollar figure is notional there). Generous enough not to trip a
# normal task, low enough to catch a runaway metered loop.
DEFAULT_API_KEY_COST_CAP_USD: float = 20.0


# USD per 1M tokens, keyed by a substring matched against the model id the SDK
# reports (e.g. "claude-opus-4-...", "claude-sonnet-4-...", "claude-haiku-...").
# Tuple is (input, output, cache_read, cache_write). Cache read is ~0.1x input
# and cache write ~1.25x input per Anthropic's published prompt-caching
# multipliers. These power the budget GUARD, not billing-accurate accounting;
# keep them roughly current. Unknown models fall back to DEFAULT_PRICING.
MODEL_PRICING: dict[str, tuple[float, float, float, float]] = {
    "opus": (15.0, 75.0, 1.5, 18.75),
    "sonnet": (3.0, 15.0, 0.30, 3.75),
    "haiku": (1.0, 5.0, 0.10, 1.25),
}
DEFAULT_PRICING: tuple[float, float, float, float] = (3.0, 15.0, 0.30, 3.75)


def _price_for(model: str) -> tuple[float, float, float, float]:
    m = (model or "").lower()
    for key, price in MODEL_PRICING.items():
        if key in m:
            return price
    return DEFAULT_PRICING


def estimate_cost_usd(usage: list[IterationUsage]) -> float:
    """Estimate metered API cost in USD from per-iteration token usage.

    This is a guard estimate, not an invoice. In subscription mode no per-token
    dollars are billed, so the number is notional there and is only ENFORCED
    when auth_mode is api_key (see _resolve_cost_cap in the orchestrator). It is
    still recorded every run so subscription runs stay cost-aware.
    """
    total = 0.0
    for u in usage:
        in_p, out_p, cr_p, cw_p = _price_for(u.model)
        total += (u.input_tokens / 1_000_000) * in_p
        total += (u.output_tokens / 1_000_000) * out_p
        total += (u.cache_read_tokens / 1_000_000) * cr_p
        total += (u.cache_creation_tokens / 1_000_000) * cw_p
    return total


def cost_cap_hit(*, estimate_usd: float, max_usd: float | None) -> bool:
    """True when a positive dollar cap is set and the estimate meets/exceeds it.

    A None or non-positive cap means "no cap" (returns False), preserving the
    pre-cost-guard behavior when no budget is configured.
    """
    if max_usd is None or max_usd <= 0:
        return False
    return estimate_usd >= max_usd
