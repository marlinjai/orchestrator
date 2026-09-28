"""The E4b race scoring rule (scripts/mercury_race.py), which decides M9.

Exit criterion decided 2026-09-28: N >= 10 goals, Mercury's median time to a
verified result lower than Claude's, and its held-out pass rate within 10
percentage points. A goal without a held-out-green attempt counts as infinitely
slow, so failing fast can never look like winning.
"""

import importlib.util
import math
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "mercury_race", Path(__file__).resolve().parent.parent / "scripts" / "mercury_race.py"
)
race = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(race)


def _rec(goal, cohort, *attempts):
    """attempts: (held_out, time_to_verified_ms) pairs."""
    return {
        "goal": goal,
        "cohort": cohort,
        "result": {
            "attempts": [{"held_out": h, "time_to_verified_ms": t} for h, t in attempts]
        },
    }


def _field(n, claude, mercury):
    """n goals; claude/mercury map goal index -> list of attempts."""
    recs = []
    for i in range(n):
        g = f"g{i:02d}"
        recs.append(_rec(g, "claude", *claude(i)))
        recs.append(_rec(g, "mercury", *mercury(i)))
    return recs


def test_mercury_wins_when_faster_and_as_accurate():
    s = race.score(_field(10, lambda i: [("pass", 60_000)], lambda i: [("pass", 20_000)]))
    assert s["claude"]["pass_rate_pct"] == 100 and s["mercury"]["pass_rate_pct"] == 100
    assert s["mercury_wins"] is True


def test_one_extra_miss_is_inside_the_band():
    s = race.score(
        _field(
            10,
            lambda i: [("pass", 60_000)],
            lambda i: [("fail", 5_000)] if i == 0 else [("pass", 20_000)],
        )
    )
    assert s["mercury"]["pass_rate_pct"] == 90
    assert s["mercury_wins"] is True


def test_two_extra_misses_lose_even_when_faster():
    s = race.score(
        _field(
            10,
            lambda i: [("pass", 60_000)],
            lambda i: [("fail", 5_000)] if i < 2 else [("pass", 1_000)],
        )
    )
    assert s["mercury"]["pass_rate_pct"] == 80
    assert s["mercury_wins"] is False


def test_failures_count_as_infinitely_slow():
    s = race.score(
        _field(
            10,
            lambda i: [("pass", 60_000)],
            lambda i: [("fail", 1)] if i < 6 else [("pass", 1)],
        )
    )
    assert math.isinf(s["mercury"]["median_ttv_ms"])
    assert s["mercury_wins"] is False


def test_best_green_attempt_is_the_goal_time():
    s = race.score([_rec("g", "claude", ("fail", 1), ("pass", 900), ("pass", 700))])
    assert s["per_goal"]["g"]["claude"] == {"passed": True, "ttv_ms": 700.0}


def test_fewer_than_ten_goals_never_wins():
    s = race.score(_field(9, lambda i: [("pass", 60_000)], lambda i: [("pass", 1)]))
    assert s["n_ok"] is False and s["mercury_wins"] is False


def test_missing_cohort_json_is_a_failed_goal():
    recs = _field(10, lambda i: [("pass", 1_000)], lambda i: [("pass", 500)])
    recs[1].pop("result")  # mercury g00 crashed before writing cohort.json
    s = race.score(recs)
    assert s["per_goal"]["g00"]["mercury"]["passed"] is False


def test_a_single_cohort_run_never_produces_a_verdict():
    recs = [_rec(f"g{i:02d}", "mercury", ("pass", 1_000)) for i in range(10)]
    s = race.score(recs)
    assert s["verdict_possible"] is False
    assert s["mercury_wins"] is False
    assert s["cohorts_ran"] == ["mercury"]


def test_attempt_stats_count_every_attempt():
    recs = [_rec("g", "mercury", ("pass", 10_000), ("fail", 30_000))]
    recs[0]["attempt_states"] = [{"iterations": 1}, {"iterations": 4}]
    a = race.score(recs)["attempts"]["mercury"]
    assert a == {"attempts": 2, "green": 1, "one_iteration": 1, "median_s": 20.0, "mean_s": 20.0}


def test_score_json_has_no_infinity_and_report_handles_missing_timings():
    import json

    s = race.score([_rec("g00", "mercury", ("pass", 5000))])
    text = json.dumps(race._json_safe(s), allow_nan=False)
    assert "Infinity" not in text
    assert json.loads(text)["claude"]["median_ttv_ms"] is None
    assert race._fmt_s(None) == "none"
    assert race._fmt_s(2.0) == "2.0s"
