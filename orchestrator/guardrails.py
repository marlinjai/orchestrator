import re
import time
from pathlib import Path


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
