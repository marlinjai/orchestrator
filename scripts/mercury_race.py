"""The E4b race: Claude vs Mercury as coding Workers on the textkit benchmark.

Decided by Marlin on 2026-09-28 (decision page 2026-09-28-mercury-race.html):
10 self-contained goals with hidden tests, the hidden tests in a verifier folder
outside every repo (``~/.orchestrator/verifier-vault/mercury-race``, accepting
that a Worker's shell could read it; the logged commands would show it),
2 attempts per goal per cohort, and Mercury counts as a winner only when its
median time to a verified result is lower AND its hidden-test pass rate is
within 10 percentage points of Claude's.

Subcommands:

  validate   prove every hidden suite is fair: it FAILS on the seed project and
             PASSES on the seed plus the goal's reference solution.
  run        install the hidden tests into the vault, then run every goal as a
             Claude cohort and a Mercury cohort (``orchestrator start --best-of``)
             with a small process pool; each cohort gets its own operator config
             home (the only difference between cohorts) and state home.
  report     score a finished run against the exit criterion.

Scoring: per goal and cohort, the result is the cohort's selected attempt (the
fastest held-out-green one). A goal passes for a cohort when any attempt is
held-out-green. A cohort's median time-to-verified is taken over ALL goals, a
goal without a green attempt counting as infinitely slow, so failing fast never
looks like winning.

Usage (from the orchestrator repo, with its venv on PATH so ``python3`` has pytest):

  python3 scripts/mercury_race.py validate
  python3 scripts/mercury_race.py run --out ~/.orchestrator/mercury-race/<date>
  python3 scripts/mercury_race.py report --out ~/.orchestrator/mercury-race/<date>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "bench" / "mercury-race"
SEED, GOALS, HELDOUT, REFERENCE = (BENCH / d for d in ("seed", "goals", "heldout", "reference"))
VAULT = Path.home() / ".orchestrator" / "verifier-vault" / "mercury-race"
COHORTS = ("claude", "mercury")
MERCURY_CONFIG = '[executors.worker]\nmodel_id = "mercury-2"\nprovider = "inception"\n'
PASS_BAND_POINTS = 10.0

# Keep pytest and Python from writing caches into the attempt worktrees: an
# untracked __pycache__ would make a clean worktree look dirty.
_QUIET_ENV = {"PYTHONDONTWRITEBYTECODE": "1"}


def goal_slugs() -> list[str]:
    return sorted(p.stem for p in GOALS.glob("*.md"))


def heldout_command(slug: str, root: Path) -> str:
    return f"python3 -m pytest -q -p no:cacheprovider {root / slug}"


def make_project(dest: Path, overlay: Path | None = None) -> Path:
    """Copy the seed (plus an optional overlay) into ``dest`` as a fresh git repo."""
    shutil.copytree(SEED, dest)
    if overlay is not None:
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    git = ["git", "-c", "user.email=race@example.invalid", "-c", "user.name=race"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dest, check=True)
    subprocess.run([*git, "add", "-A"], cwd=dest, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "seed"], cwd=dest, check=True)
    return dest


def _pytest(target: Path, cwd: Path) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target)],
        cwd=cwd,
        env={**os.environ, **_QUIET_ENV},
        capture_output=True,
        text=True,
    ).returncode


def cmd_validate(_args) -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for slug in goal_slugs():
            seed = make_project(Path(tmp) / f"{slug}-seed")
            ref = make_project(Path(tmp) / f"{slug}-ref", REFERENCE / slug)
            fails_on_seed = _pytest(HELDOUT / slug, seed) != 0
            passes_on_ref = _pytest(HELDOUT / slug, ref) == 0
            visible_ok = _pytest(ref / "tests", ref) == 0
            ok = fails_on_seed and passes_on_ref and visible_ok
            bad += not ok
            print(
                f"{'ok  ' if ok else 'FAIL'} {slug}: fails on seed={fails_on_seed} "
                f"passes on reference={passes_on_ref} seed tests still pass={visible_ok}"
            )
    print("all hidden suites are fair" if not bad else f"{bad} goal(s) are not fair")
    return 1 if bad else 0


def install_vault() -> None:
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    if VAULT.exists():
        shutil.rmtree(VAULT)
    shutil.copytree(HELDOUT, VAULT)


def _run_one(out: Path, slug: str, cohort: str, attempts: int, max_iterations: int) -> dict:
    base = out / cohort / slug
    project = make_project(base / "project")
    cfg_home = base / "config"
    cfg_home.mkdir(parents=True)
    if cohort == "mercury":
        (cfg_home / "config.toml").write_text(MERCURY_CONFIG)
    home = base / "home"
    task_id = f"race-{cohort}-{slug}"
    env = {
        **os.environ,
        **_QUIET_ENV,
        "ORCHESTRATOR_CONFIG_HOME": str(cfg_home),
        "ORCHESTRATOR_HOME": str(home),
    }
    cmd = [
        "orchestrator", "start",
        "--goal", str(GOALS / f"{slug}.md"),
        "--project", str(project),
        "--task-id", task_id,
        "--best-of", str(attempts),
        "--max-iterations", str(max_iterations),
        "--max-hours", "0.75",
        "--held-out", heldout_command(slug, VAULT),
    ]
    with open(base / "run.out", "w") as log:
        proc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    cohort_file = home / "tasks" / task_id / "cohort.json"
    single_state = home / "tasks" / task_id / "state.json"
    record = {"goal": slug, "cohort": cohort, "exit_code": proc.returncode}
    if cohort_file.exists():
        record["result"] = json.loads(cohort_file.read_text())
    elif single_state.exists():
        # --best-of 1 takes the single-run path, which writes no cohort.json:
        # score its one attempt from state.json the same way best-of would.
        record["result"] = _single_run_cohort(task_id, json.loads(single_state.read_text()))
    if "result" in record:
        record["attempt_states"] = [
            _state_summary(home / "tasks" / a["task_id"] / "state.json")
            for a in record["result"].get("attempts", [])
        ]
    print(f"done {cohort:7} {slug}: {record.get('result', {}).get('status', 'no cohort.json')}", flush=True)
    return record


def _single_run_cohort(task_id: str, state: dict) -> dict:
    """A one-attempt cohort record in best-of's shape, built from a single run."""
    held = (state.get("last_held_out") or {}).get("status")
    ttv = sum(u.get("worker_ms", 0) + u.get("proxy_ms", 0) for u in state.get("usage", []))
    return {
        "task_id": task_id,
        "n": 1,
        "status": state.get("status"),
        "attempts": [
            {"task_id": task_id, "status": state.get("status"), "held_out": held, "time_to_verified_ms": ttv}
        ],
    }


def _state_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    s = json.loads(path.read_text())
    workers = [r for r in s.get("executor_records", []) if r.get("role") == "worker"]

    def total(key):
        vals = [r.get(key) for r in workers if r.get(key) is not None]
        return sum(vals) if vals else None

    return {
        "status": s.get("status"),
        "iterations": s.get("iteration"),
        "worker_ms": sum(u.get("worker_ms", 0) for u in s.get("usage", [])),
        "proxy_ms": sum(u.get("proxy_ms", 0) for u in s.get("usage", [])),
        "calls": total("call_count"),
        "ttft_ms": total("total_ttft_ms"),
        "generation_ms": total("total_generation_ms"),
        "tool_ms": total("total_tool_ms"),
        "server_ms": total("total_server_ms"),
        "est_cost_usd": s.get("estimated_cost_usd"),
    }


def cmd_run(args) -> int:
    out = Path(args.out).expanduser()
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty; pick a fresh --out", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    install_vault()
    slugs = [g for g in goal_slugs() if not args.goals or g in args.goals.split(",")]
    cohorts = [c for c in COHORTS if not args.cohorts or c in args.cohorts.split(",")]
    jobs = [(slug, cohort) for slug in slugs for cohort in cohorts]

    def _safe(j):
        try:
            return _run_one(out, j[0], j[1], args.attempts, args.max_iterations)
        except Exception as e:  # keep the other records
            print(f"error {j[1]:7} {j[0]}: {e!r}", flush=True)
            return {"goal": j[0], "cohort": j[1], "exit_code": None, "error": repr(e)}

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        records = list(pool.map(_safe, jobs))
    (out / "results.json").write_text(json.dumps(records, indent=2))
    print(f"results: {out / 'results.json'}")
    return cmd_report(args)


def _goal_outcome(record: dict) -> tuple[bool, float]:
    result = record.get("result") or {}
    greens = [a for a in result.get("attempts", []) if a.get("held_out") == "pass"]
    if not greens:
        return False, math.inf
    return True, float(min(a["time_to_verified_ms"] for a in greens))


def score(records: list[dict]) -> dict:
    by = {c: {} for c in COHORTS}
    for r in records:
        by[r["cohort"]][r["goal"]] = _goal_outcome(r)
    goals = sorted(set(by["claude"]) | set(by["mercury"]))
    summary = {}
    for c in COHORTS:
        outcomes = [by[c].get(g, (False, math.inf)) for g in goals]
        passed = sum(1 for ok, _ in outcomes if ok)
        summary[c] = {
            "goals": len(goals),
            "passed": passed,
            "pass_rate_pct": 100.0 * passed / len(goals) if goals else 0.0,
            "median_ttv_ms": statistics.median([t for _, t in outcomes]) if goals else math.inf,
        }
    faster = summary["mercury"]["median_ttv_ms"] < summary["claude"]["median_ttv_ms"]
    within_band = (
        summary["mercury"]["pass_rate_pct"] >= summary["claude"]["pass_rate_pct"] - PASS_BAND_POINTS
    )
    summary["n_ok"] = len(goals) >= 10
    summary["mercury_wins"] = bool(faster and within_band and summary["n_ok"])
    summary["per_goal"] = {
        g: {c: {"passed": by[c].get(g, (False, math.inf))[0], "ttv_ms": by[c].get(g, (False, math.inf))[1]} for c in COHORTS}
        for g in goals
    }
    return summary


def _fmt_ms(v: float) -> str:
    return "none" if math.isinf(v) else f"{v / 1000:.1f}s"


def cmd_report(args) -> int:
    out = Path(args.out).expanduser()
    records = json.loads((out / "results.json").read_text())
    s = score(records)
    lines = ["| Goal | Claude | Mercury |", "|---|---|---|"]
    for g, row in s["per_goal"].items():
        cells = [
            f"{'pass' if row[c]['passed'] else 'FAIL'} {_fmt_ms(row[c]['ttv_ms'])}" for c in COHORTS
        ]
        lines.append(f"| {g} | {cells[0]} | {cells[1]} |")
    for c in COHORTS:
        lines.append(
            f"\n{c}: {s[c]['passed']}/{s[c]['goals']} held-out green "
            f"({s[c]['pass_rate_pct']:.0f}%), median time to verified {_fmt_ms(s[c]['median_ttv_ms'])}"
        )
    lines.append(
        f"\nExit criterion (N >= 10, Mercury median faster, pass rate within "
        f"{PASS_BAND_POINTS:.0f} points): {'MERCURY WINS' if s['mercury_wins'] else 'Mercury does not win'}"
    )
    text = "\n".join(lines)
    (out / "report.md").write_text(text + "\n")
    (out / "score.json").write_text(json.dumps(s, indent=2, default=str))
    print(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mercury_race")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    for name in ("run", "report"):
        sp = sub.add_parser(name)
        sp.add_argument("--out", required=True)
        if name == "run":
            sp.add_argument("--attempts", type=int, default=2)
            sp.add_argument("--parallel", type=int, default=3)
            sp.add_argument("--max-iterations", type=int, default=8)
            sp.add_argument("--goals", default="", help="comma-separated subset (a dry run)")
            sp.add_argument("--cohorts", default="", help="comma-separated subset, e.g. mercury (a remeasure)")
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
