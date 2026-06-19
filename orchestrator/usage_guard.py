"""Fleet-wide usage guards above the per-run caps (Wave 0 reliability core).

The per-run iteration / wall-clock / token caps in guardrails.py bound a SINGLE
orchestrator run. These guards bound the whole fleet on the shared
ORCHESTRATOR_HOME:

- a global STOP file: an operator panic button that halts EVERY run at its next
  iteration boundary, distinct from the per-task STOP kill switch;
- a rolling daily token budget tracked in an append-only shared ledger, so many
  runs in one day cannot collectively exhaust the Anthropic rate-limit / quota
  even when each stays under its own per-run ceiling.

Both are operator-owned and un-promptable: a goal file cannot relax them
(mirrors the irreversible_ops hard-escalate rule). The daily cap defaults OFF
(0); on the flat subscription dollars are notional, so the operator opts into a
token ceiling only if they want one. The ledger is append-only with one line per
iteration, so concurrent runs never corrupt each other's rows.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

GLOBAL_STOP_FILENAME = "GLOBAL_STOP"
USAGE_LEDGER_FILENAME = "usage-ledger.jsonl"
DAILY_WINDOW_HOURS = 24.0


def global_stop_path(home: Path) -> Path:
    return home / GLOBAL_STOP_FILENAME


def global_kill_active(home: Path) -> bool:
    """True when the operator has touched the fleet-wide STOP file."""
    return global_stop_path(home).exists()


def usage_ledger_path(home: Path) -> Path:
    return home / USAGE_LEDGER_FILENAME


def record_usage(
    home: Path,
    *,
    task_id: str,
    iteration: int,
    tokens: int,
    now: datetime | None = None,
) -> None:
    """Append one iteration's token total to the shared ledger.

    Append-only and one line per call, so two runs writing concurrently never
    clobber each other. A non-positive token count is a no-op (nothing to bill
    against the daily budget)."""
    if tokens <= 0:
        return
    stamp = now or datetime.now(timezone.utc)
    path = usage_ledger_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = json.dumps(
        {
            "ts": stamp.isoformat(),
            "task_id": task_id,
            "iteration": iteration,
            "tokens": int(tokens),
        },
        ensure_ascii=False,
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(row + "\n")


def tokens_in_window(
    home: Path,
    *,
    window_hours: float = DAILY_WINDOW_HOURS,
    now: datetime | None = None,
) -> int:
    """Sum tokens recorded across ALL runs in the trailing window.

    Malformed or undated lines are skipped so one bad append never blocks the
    guard (same robustness as the decision ledger reader)."""
    path = usage_ledger_path(home)
    if not path.exists():
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=window_hours)
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            ts = datetime.fromisoformat(data["ts"])
            tokens = int(data["tokens"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
        if ts >= cutoff:
            total += tokens
    return total


def daily_cap_hit(*, tokens_today: int, daily_cap: int | None) -> bool:
    """True when a positive daily token budget is set and today's fleet-wide
    usage meets or exceeds it. None or non-positive means "no cap"."""
    if daily_cap is None or daily_cap <= 0:
        return False
    return tokens_today >= daily_cap
