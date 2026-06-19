from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.usage_guard import (
    daily_cap_hit,
    global_kill_active,
    global_stop_path,
    record_usage,
    tokens_in_window,
    usage_ledger_path,
)


def test_global_kill_inactive_then_active(tmp_path: Path):
    assert not global_kill_active(tmp_path)
    global_stop_path(tmp_path).touch()
    assert global_kill_active(tmp_path)


def test_record_usage_appends_and_sums(tmp_path: Path):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    record_usage(tmp_path, task_id="a", iteration=1, tokens=100, now=now)
    record_usage(tmp_path, task_id="b", iteration=1, tokens=250, now=now)
    # Two different runs writing to the same fleet ledger both count.
    assert tokens_in_window(tmp_path, now=now) == 350


def test_record_usage_ignores_nonpositive(tmp_path: Path):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    record_usage(tmp_path, task_id="a", iteration=1, tokens=0, now=now)
    record_usage(tmp_path, task_id="a", iteration=2, tokens=-5, now=now)
    assert not usage_ledger_path(tmp_path).exists()
    assert tokens_in_window(tmp_path, now=now) == 0


def test_tokens_in_window_excludes_old_rows(tmp_path: Path):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    record_usage(tmp_path, task_id="old", iteration=1, tokens=999, now=now - timedelta(hours=30))
    record_usage(tmp_path, task_id="fresh", iteration=1, tokens=5, now=now - timedelta(hours=1))
    assert tokens_in_window(tmp_path, now=now) == 5


def test_tokens_in_window_no_ledger(tmp_path: Path):
    assert tokens_in_window(tmp_path) == 0


def test_tokens_in_window_skips_malformed_lines(tmp_path: Path):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    path = usage_ledger_path(tmp_path)
    path.write_text(
        'not json\n'
        '{"ts": "not a date", "tokens": 10}\n'
        '{"ts": "%s", "tokens": 42}\n' % (now - timedelta(hours=1)).isoformat()
    )
    assert tokens_in_window(tmp_path, now=now) == 42


def test_daily_cap_hit():
    assert not daily_cap_hit(tokens_today=5_000, daily_cap=None)
    assert not daily_cap_hit(tokens_today=5_000, daily_cap=0)
    assert not daily_cap_hit(tokens_today=4_999, daily_cap=5_000)
    assert daily_cap_hit(tokens_today=5_000, daily_cap=5_000)
    assert daily_cap_hit(tokens_today=6_000, daily_cap=5_000)
