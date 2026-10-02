"""The E4b race scoring rule (scripts/mercury_race.py), which decides M9.

Exit criterion decided 2026-09-28: N >= 10 goals, Mercury's median time to a
verified result lower than Claude's, and its held-out pass rate within 10
percentage points. A goal without a held-out-green attempt counts as infinitely
slow, so failing fast can never look like winning.
"""

import importlib.util
import json
import math
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mercury_race", Path(__file__).resolve().parent.parent / "scripts" / "mercury_race.py"
)
race = importlib.util.module_from_spec(_SPEC)
sys.modules["mercury_race"] = race  # dataclasses look their module up while it executes
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


# ---- round two: repo benches ----

def _write_bench(root: Path, base: Path, **overrides) -> Path:
    bench = root / "bench"
    (bench / "goals").mkdir(parents=True)
    (bench / "goals" / "01-first.md").write_text("---\nverify: true\n---\n# first\n")
    (bench / "goals" / "02-second.md").write_text("---\nverify: true\n---\n# second\n")
    fields = {
        "name": "demo",
        "base": str(base),
        "setup": "touch .prepared",
        "held_out": 'verifier demo {goal} "$PWD"',
        "trees": str(root / "trees"),
        **overrides,
    }
    (bench / "bench.toml").write_text(
        "".join(f"{k} = {json.dumps(v)}\n" for k, v in fields.items() if v is not None)
    )
    return bench


def _base_repo(root: Path) -> Path:
    base = root / "base"
    base.mkdir()
    (base / "README.md").write_text("base\n")
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=base, check=True)
    subprocess.run([*git, "add", "-A"], cwd=base, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], cwd=base, check=True)
    return base


def _fake_orchestrator(bin_dir: Path, outcomes: dict[str, dict]) -> None:
    """An `orchestrator` on PATH that records its arguments and writes the
    state.json a real run would leave. `outcomes` maps a task id to
    {"held_out": ..., "ms": ...}; a task id not listed writes no state at all."""
    bin_dir.mkdir()
    script = bin_dir / "orchestrator"
    script.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
opt = dict(zip(args[1::2], args[2::2]))
task = opt["--task-id"]
home = Path(os.environ["ORCHESTRATOR_HOME"]) / "tasks" / task
home.mkdir(parents=True)
(home / "argv.json").write_text(json.dumps({{"args": args, "prepared": (Path(opt["--project"]) / ".prepared").exists(),
    "config": (Path(os.environ["ORCHESTRATOR_CONFIG_HOME"]) / "config.toml").exists()}}))
outcome = {json.dumps(outcomes)}.get(task)
if outcome is not None:
    (home / "state.json").write_text(json.dumps({{
        "status": "completed" if outcome["held_out"] == "pass" else "escalated", "iteration": 1,
        "last_held_out": {{"status": outcome["held_out"]}},
        "usage": [{{"worker_ms": outcome["ms"], "proxy_ms": 0}}], "executor_records": []}}))
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def test_load_bench_reads_the_manifest(tmp_path):
    bench = race.load_bench(_write_bench(tmp_path, tmp_path / "base"))
    assert bench.name == "demo" and bench.setup == "touch .prepared"
    assert bench.goal_slugs() == ["01-first", "02-second"]
    assert bench.base == tmp_path / "base" and bench.trees == tmp_path / "trees"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"trees": None}, "missing or empty trees"),
        ({"held_out": "verifier demo"}, "must contain {goal}"),
        ({"setup": " "}, "setup must be a non-empty string"),
        ({"name": ""}, "missing or empty name"),
    ],
)
def test_load_bench_refuses_a_malformed_manifest(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        race.load_bench(_write_bench(tmp_path, tmp_path / "base", **overrides))


def test_load_bench_refuses_a_bench_without_goals(tmp_path):
    bench = _write_bench(tmp_path, tmp_path / "base")
    for goal in (bench / "goals").glob("*.md"):
        goal.unlink()
    with pytest.raises(ValueError, match="no goal files"):
        race.load_bench(bench)


def test_repo_bench_run_prepares_a_clone_per_attempt_and_scores_like_best_of(tmp_path, monkeypatch):
    base = _base_repo(tmp_path)
    bench = _write_bench(tmp_path, base)
    _fake_orchestrator(
        tmp_path / "bin",
        {
            "race-mercury-demo-01-first-attempt-0": {"held_out": "fail", "ms": 100},
            "race-mercury-demo-01-first-attempt-1": {"held_out": "pass", "ms": 900},
            "race-mercury-demo-02-second-attempt-0": {"held_out": "pass", "ms": 700},
            "race-mercury-demo-02-second-attempt-1": {"held_out": "pass", "ms": 300},
        },
    )
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    out = tmp_path / "out"
    code = race.main(
        ["run", "--out", str(out), "--bench", str(bench), "--cohorts", "mercury", "--attempts", "2", "--parallel", "2"]
    )
    assert code == 0
    records = {r["goal"]: r for r in json.loads((out / "results.json").read_text())}
    assert sorted(records) == ["demo-01-first", "demo-02-second"]

    first = records["demo-01-first"]["result"]
    assert [a["held_out"] for a in first["attempts"]] == ["fail", "pass"]
    assert [a["selected"] for a in first["attempts"]] == [False, True]
    second = records["demo-02-second"]["result"]
    assert [a["selected"] for a in second["attempts"]] == [False, True]  # the faster green one
    assert race._goal_outcome(records["demo-02-second"]) == (True, 300.0)

    # Each attempt ran in its own prepared clone, with the goal's hidden-test command.
    seen = json.loads(
        (out / "mercury" / "demo-01-first" / "home" / "tasks" / "race-mercury-demo-01-first-attempt-1" / "argv.json").read_text()
    )
    opt = dict(zip(seen["args"][1::2], seen["args"][2::2]))
    tree = Path(opt["--project"])
    assert tree == tmp_path / "trees" / "out" / "mercury" / "demo-01-first" / "attempt-1"
    assert (tree / ".git").is_dir() and (tree / "README.md").read_text() == "base\n"
    assert seen["prepared"] is True and seen["config"] is True
    assert opt["--held-out"] == 'verifier demo 01-first "$PWD"'
    assert opt["--goal"] == str(bench.resolve() / "goals" / "01-first.md")
    assert "--best-of" not in seen["args"]
    assert "2/2 goals held-out green" in (out / "report.md").read_text()


def test_repo_bench_setup_failure_and_a_run_without_state_are_failed_attempts(tmp_path, monkeypatch):
    base = _base_repo(tmp_path)
    failing = _write_bench(tmp_path / "a", base, setup="exit 3")
    _fake_orchestrator(tmp_path / "bin", {})
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    out = tmp_path / "out-a"
    out.mkdir()
    record = race._run_repo_goal(out, race.load_bench(failing), "01-first", "claude", 2, 8)
    assert [a["status"] for a in record["result"]["attempts"]] == ["setup-failed", "setup-failed"]
    assert record["result"]["status"] == "no-green-attempt"
    assert race._goal_outcome(record) == (False, math.inf)

    # Setup works, but the orchestrator leaves no state: still a failed attempt, not a crash.
    working = _write_bench(tmp_path / "b", base)
    out_b = tmp_path / "out-b"
    out_b.mkdir()
    record = race._run_repo_goal(out_b, race.load_bench(working), "01-first", "claude", 1, 8)
    assert record["result"]["attempts"][0]["held_out"] is None
    assert race._goal_outcome(record) == (False, math.inf)
    # The Claude cohort gets no executor config: the default Worker.
    assert not (out_b / "claude" / "demo-01-first" / "config" / "config.toml").exists()


def test_goal_filter_accepts_a_slug_or_a_goal_id(tmp_path, monkeypatch):
    base = _base_repo(tmp_path)
    bench = _write_bench(tmp_path, base)
    _fake_orchestrator(tmp_path / "bin", {})
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    out = tmp_path / "out"
    race.main(["run", "--out", str(out), "--bench", str(bench), "--cohorts", "claude",
               "--attempts", "1", "--goals", "demo-02-second"])
    assert [r["goal"] for r in json.loads((out / "results.json").read_text())] == ["demo-02-second"]


def test_a_malformed_bench_stops_the_run_before_anything_starts(tmp_path, capsys):
    bench = _write_bench(tmp_path, tmp_path / "base", held_out="no placeholder")
    assert race.main(["run", "--out", str(tmp_path / "out"), "--bench", str(bench)]) == 2
    assert "must contain {goal}" in capsys.readouterr().err

