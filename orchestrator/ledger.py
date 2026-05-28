import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LedgerEntry:
    ts: str
    task_id: str
    iteration: int
    category: str
    effective_mode: str
    proxy_choice: str
    proxy_reason: str
    executed: bool
    actual_choice: str | None = None
    agreed: bool | None = None
    tokens_in: int = 0
    wall_ms: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": self.ts,
                "task_id": self.task_id,
                "iteration": self.iteration,
                "category": self.category,
                "effective_mode": self.effective_mode,
                "proxy_choice": self.proxy_choice,
                "proxy_reason": self.proxy_reason,
                "executed": self.executed,
                "actual_choice": self.actual_choice,
                "agreed": self.agreed,
                "tokens_in": self.tokens_in,
                "wall_ms": self.wall_ms,
            },
            ensure_ascii=False,
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_decision(ledger_path: Path, entry: LedgerEntry) -> None:
    """Append one decision row as JSONL. Append-only: never rewrites existing
    rows, so the ledger cannot be corrupted by a partial write of prior data.
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(entry.to_json() + "\n")


def append_note(notes_path: Path, line: str) -> None:
    """Append one human-readable lab-note line. A future Worker reads this to
    rehydrate context in seconds without parsing the JSONL ledger.
    """
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    stamped = f"- {now_iso()} {line.strip()}"
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(stamped + "\n")


def read_entries(ledger_path: Path) -> list[LedgerEntry]:
    """Read all ledger rows. Skips malformed lines rather than failing the whole
    read, so one bad append never blocks a review.
    """
    if not ledger_path.exists():
        return []
    entries: list[LedgerEntry] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(
            LedgerEntry(
                ts=data.get("ts", ""),
                task_id=data.get("task_id", ""),
                iteration=data.get("iteration", 0),
                category=data.get("category", "unknown"),
                effective_mode=data.get("effective_mode", ""),
                proxy_choice=data.get("proxy_choice", ""),
                proxy_reason=data.get("proxy_reason", ""),
                executed=data.get("executed", False),
                actual_choice=data.get("actual_choice"),
                agreed=data.get("agreed"),
                tokens_in=data.get("tokens_in", 0),
                wall_ms=data.get("wall_ms", 0),
            )
        )
    return entries


@dataclass
class CategoryAgreement:
    category: str
    total: int
    judged: int          # rows where actual_choice is known
    agreed: int
    agreement_rate: float | None  # None when nothing has been judged yet


def agreement_by_category(entries: list[LedgerEntry]) -> dict[str, CategoryAgreement]:
    """Aggregate agreement rate per category. Only rows with a known
    actual_choice count toward the rate; a category seen only in live mode
    (never judged) reports agreement_rate=None.
    """
    totals: dict[str, int] = defaultdict(int)
    judged: dict[str, int] = defaultdict(int)
    agreed: dict[str, int] = defaultdict(int)

    for e in entries:
        totals[e.category] += 1
        if e.agreed is not None:
            judged[e.category] += 1
            if e.agreed:
                agreed[e.category] += 1

    out: dict[str, CategoryAgreement] = {}
    for cat in totals:
        j = judged[cat]
        rate = (agreed[cat] / j) if j else None
        out[cat] = CategoryAgreement(
            category=cat,
            total=totals[cat],
            judged=j,
            agreed=agreed[cat],
            agreement_rate=rate,
        )
    return out
