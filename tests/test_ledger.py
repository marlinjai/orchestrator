from orchestrator.ledger import (
    LedgerEntry,
    agreement_by_category,
    append_decision,
    append_note,
    now_iso,
    read_entries,
)


def _entry(**kw) -> LedgerEntry:
    base = dict(
        ts=now_iso(),
        task_id="t1",
        iteration=1,
        category="merge_after_verify",
        effective_mode="live",
        proxy_choice="auto_approve",
        proxy_reason="verify green",
        executed=True,
    )
    base.update(kw)
    return LedgerEntry(**base)


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "ledger.jsonl"
    append_decision(p, _entry())
    append_decision(p, _entry(category="branch_cleanup", iteration=2))
    entries = read_entries(p)
    assert len(entries) == 2
    assert entries[0].category == "merge_after_verify"
    assert entries[1].category == "branch_cleanup"


def test_append_is_append_only(tmp_path):
    p = tmp_path / "ledger.jsonl"
    append_decision(p, _entry(iteration=1))
    append_decision(p, _entry(iteration=2))
    append_decision(p, _entry(iteration=3))
    assert len(p.read_text().splitlines()) == 3


def test_read_skips_malformed_lines(tmp_path):
    p = tmp_path / "ledger.jsonl"
    append_decision(p, _entry())
    with p.open("a") as f:
        f.write("this is not json\n")
    append_decision(p, _entry(iteration=2))
    assert len(read_entries(p)) == 2


def test_read_missing_file_returns_empty(tmp_path):
    assert read_entries(tmp_path / "nope.jsonl") == []


def test_append_note_stamps_and_appends(tmp_path):
    p = tmp_path / "notes.md"
    append_note(p, "merged PR #87")
    append_note(p, "cleaned 3 branches")
    lines = p.read_text().splitlines()
    assert len(lines) == 2
    assert "merged PR #87" in lines[0]
    assert lines[0].startswith("- ")


def test_agreement_by_category_computes_rate(tmp_path):
    entries = [
        _entry(category="status_fetch", agreed=True),
        _entry(category="status_fetch", agreed=True),
        _entry(category="status_fetch", agreed=False),
        _entry(category="scope_change", agreed=None),  # never judged
    ]
    agg = agreement_by_category(entries)
    assert agg["status_fetch"].total == 3
    assert agg["status_fetch"].judged == 3
    assert abs(agg["status_fetch"].agreement_rate - (2 / 3)) < 1e-9
    assert agg["scope_change"].agreement_rate is None
