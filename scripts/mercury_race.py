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

Round two, on real repositories (decided 2026-10-02, bench/mercury-round-two):
``run --bench <dir>`` (repeatable) races the goals of a repo bench instead of
the textkit benchmark. A repo bench is a directory with ``bench.toml`` and
``goals/``; every attempt gets a fresh clone of the bench's base repo, prepared
by the bench's setup command, and the hidden tests are run by the bench's
held-out command (on hermes: a verifier that runs them as another OS user and
answers only PASS or FAIL). The harness runs the attempts itself, one
``orchestrator start`` each, because a best-of worktree would start without the
repo's installed dependencies. Scoring and the exit criterion are the same.

  python3 scripts/mercury_race.py run --out <dir> \\
      --bench bench/mercury-round-two/email-editor --bench bench/mercury-round-two/hud
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
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RepoBench:
    """A bench on a real repository (round two), read from ``<dir>/bench.toml``.

    ``base``: the git repo every attempt tree is cloned from. ``setup``: a shell
    command run in a fresh tree before the Worker starts (install, build), or
    None. ``held_out``: the hidden-test command, run by the orchestrator with
    the attempt tree as its working directory; ``{goal}`` in it is replaced by
    the goal's slug. ``trees``: where attempt trees are created (it must be
    readable by whoever runs the hidden tests).
    """

    name: str
    goals: Path
    base: Path
    setup: str | None
    held_out: str
    trees: Path

    def goal_slugs(self) -> list[str]:
        return sorted(p.stem for p in self.goals.glob("*.md"))


def load_bench(path: Path) -> RepoBench:
    """Read ``<path>/bench.toml``. A malformed manifest is an error, never a
    silently different race."""
    path = Path(path).expanduser().resolve()
    manifest = path / "bench.toml"
    try:
        data = tomllib.loads(manifest.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ValueError(f"cannot read {manifest}: {e}") from e
    missing = [k for k in ("name", "base", "held_out", "trees") if not isinstance(data.get(k), str) or not data[k]]
    if missing:
        raise ValueError(f"{manifest}: missing or empty {', '.join(missing)}")
    if "{goal}" not in data["held_out"]:
        raise ValueError(f"{manifest}: held_out must contain {{goal}}, or every goal would run the same hidden tests")
    setup = data.get("setup")
    if setup is not None and (not isinstance(setup, str) or not setup.strip()):
        raise ValueError(f"{manifest}: setup must be a non-empty string when given")
    goals = path / "goals"
    if not any(goals.glob("*.md")):
        raise ValueError(f"{goals}: no goal files")
    return RepoBench(
        name=data["name"],
        goals=goals,
        base=Path(data["base"]).expanduser(),
        setup=setup,
        held_out=data["held_out"],
        trees=Path(data["trees"]).expanduser(),
    )


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


def _prepare_tree(bench: RepoBench, tree: Path, log) -> bool:
    """A fresh clone of the bench's base, set up for the Worker. False (with the
    reason in the log) when the clone or the setup command fails."""
    tree.parent.mkdir(parents=True, exist_ok=True)
    steps = [
        (["git", "clone", "-q", str(bench.base), str(tree)], None),
        (["git", "config", "user.email", "race@example.invalid"], tree),
        (["git", "config", "user.name", "race"], tree),
    ]
    for argv, cwd in steps:
        if subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT).returncode != 0:
            return False
    if bench.setup is None:
        return True
    return subprocess.run(bench.setup, shell=True, cwd=tree, stdout=log, stderr=subprocess.STDOUT).returncode == 0


def _run_repo_goal(
    out: Path, bench: RepoBench, slug: str, cohort: str, attempts: int, max_iterations: int
) -> dict:
    """One goal of a repo bench for one cohort: ``attempts`` single runs, each
    in its own prepared clone, folded into the record shape best-of produces."""
    goal_id = f"{bench.name}-{slug}"
    base = out / cohort / goal_id
    cfg_home = base / "config"
    cfg_home.mkdir(parents=True)
    if cohort == "mercury":
        (cfg_home / "config.toml").write_text(MERCURY_CONFIG)
    home = base / "home"
    env = {**os.environ, "ORCHESTRATOR_CONFIG_HOME": str(cfg_home), "ORCHESTRATOR_HOME": str(home)}
    attempt_records: list[dict] = []
    with open(base / "run.out", "w") as log:
        for i in range(attempts):
            task_id = f"race-{cohort}-{goal_id}-attempt-{i}"
            tree = bench.trees / out.name / cohort / goal_id / f"attempt-{i}"
            print(f"=== attempt {i}: {tree}", file=log, flush=True)
            if not _prepare_tree(bench, tree, log):
                attempt_records.append(
                    {"attempt_index": i, "task_id": task_id, "status": "setup-failed",
                     "held_out": None, "time_to_verified_ms": 0}
                )
                continue
            cmd = [
                "orchestrator", "start",
                "--goal", str(bench.goals / f"{slug}.md"),
                "--project", str(tree),
                "--task-id", task_id,
                "--max-iterations", str(max_iterations),
                "--max-hours", "0.75",
                "--held-out", bench.held_out.replace("{goal}", slug),
            ]
            subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            state_path = home / "tasks" / task_id / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            attempt = _single_run_cohort(task_id, state)["attempts"][0]
            attempt_records.append({"attempt_index": i, **attempt, "tree": str(tree)})
    greens = [a for a in attempt_records if a.get("held_out") == "pass"]
    selected = min(greens, key=lambda a: a["time_to_verified_ms"]) if greens else None
    for a in attempt_records:
        a["selected"] = a is selected
    result = {
        "task_id": f"race-{cohort}-{goal_id}",
        "n": attempts,
        "status": "completed" if selected else "no-green-attempt",
        "attempts": attempt_records,
    }
    record = {
        "goal": goal_id,
        "cohort": cohort,
        "exit_code": 0 if selected else 1,
        "result": result,
        "attempt_states": [
            _state_summary(home / "tasks" / a["task_id"] / "state.json") for a in attempt_records
        ],
    }
    print(f"done {cohort:7} {goal_id}: {result['status']}", flush=True)
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
    wanted = args.goals.split(",") if args.goals else None
    cohorts = [c for c in COHORTS if not args.cohorts or c in args.cohorts.split(",")]
    if args.bench:
        try:
            benches = [load_bench(Path(b)) for b in args.bench]
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        # (goal id, cohort, runner): a repo bench runs its own attempts.
        jobs = [
            (f"{b.name}-{slug}", cohort, lambda b=b, slug=slug, cohort=cohort: _run_repo_goal(
                out, b, slug, cohort, args.attempts, args.max_iterations))
            for b in benches
            for slug in b.goal_slugs()
            if wanted is None or slug in wanted or f"{b.name}-{slug}" in wanted
            for cohort in cohorts
        ]
    else:
        install_vault()
        jobs = [
            (slug, cohort, lambda slug=slug, cohort=cohort: _run_one(
                out, slug, cohort, args.attempts, args.max_iterations))
            for slug in goal_slugs()
            if wanted is None or slug in wanted
            for cohort in cohorts
        ]

    def _safe(j):
        try:
            return j[2]()
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
    ran = [c for c in COHORTS if by[c]]
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
    # A verdict needs BOTH cohorts: an absent cohort would otherwise score as 0%
    # green and infinitely slow, and hand the other one a meaningless win.
    summary["cohorts_ran"] = ran
    summary["verdict_possible"] = len(ran) == len(COHORTS)
    summary["mercury_wins"] = bool(
        faster and within_band and summary["n_ok"] and summary["verdict_possible"]
    )
    summary["attempts"] = {c: _attempt_stats([r for r in records if r["cohort"] == c]) for c in ran}
    summary["per_goal"] = {
        g: {c: {"passed": by[c].get(g, (False, math.inf))[0], "ttv_ms": by[c].get(g, (False, math.inf))[1]} for c in COHORTS}
        for g in goals
    }
    return summary


def _attempt_stats(records: list[dict]) -> dict:
    """Per-attempt view (what best-of-N hides): every attempt, not the best per goal."""
    atts = [a for r in records for a in (r.get("result") or {}).get("attempts", [])]
    states = [st for r in records for st in r.get("attempt_states", [])]
    ttv = [a.get("time_to_verified_ms", 0) / 1000 for a in atts]
    return {
        "attempts": len(atts),
        "green": sum(1 for a in atts if a.get("held_out") == "pass"),
        "one_iteration": sum(1 for st in states if st.get("iterations") == 1),
        "median_s": statistics.median(ttv) if ttv else None,
        "mean_s": statistics.mean(ttv) if ttv else None,
    }


def _json_safe(v):
    """Non-finite floats (the internal 'infinitely slow' marker) become null: a
    bare Infinity is not valid JSON."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def _fmt_s(v: float | None) -> str:
    return "none" if v is None else f"{v:.1f}s"


def _fmt_ms(v: float) -> str:
    return "none" if math.isinf(v) else f"{v / 1000:.1f}s"


def cmd_report(args) -> int:
    out = Path(args.out).expanduser()
    records = json.loads((out / "results.json").read_text())
    s = score(records)
    ran = s["cohorts_ran"]
    lines = ["| Goal | " + " | ".join(c.capitalize() for c in ran) + " |", "|---|" + "---|" * len(ran)]
    for g, row in s["per_goal"].items():
        cells = [f"{'pass' if row[c]['passed'] else 'FAIL'} {_fmt_ms(row[c]['ttv_ms'])}" for c in ran]
        lines.append(f"| {g} | " + " | ".join(cells) + " |")
    for c in ran:
        a = s["attempts"][c]
        lines.append(
            f"\n{c}: {s[c]['passed']}/{s[c]['goals']} goals held-out green "
            f"({s[c]['pass_rate_pct']:.0f}%), median time to verified {_fmt_ms(s[c]['median_ttv_ms'])}; "
            f"per attempt: {a['green']}/{a['attempts']} green, {a['one_iteration']}/{a['attempts']} in one "
            f"iteration, median {_fmt_s(a['median_s'])}, mean {_fmt_s(a['mean_s'])}"
        )
    if s["verdict_possible"]:
        lines.append(
            f"\nExit criterion (N >= 10, Mercury median faster, pass rate within "
            f"{PASS_BAND_POINTS:.0f} points): {'MERCURY WINS' if s['mercury_wins'] else 'Mercury does not win'}"
        )
    else:
        lines.append(f"\nNo verdict: only the {', '.join(ran)} cohort ran (a remeasure, not a race).")
    text = "\n".join(lines)
    (out / "report.md").write_text(text + "\n")
    (out / "score.json").write_text(json.dumps(_json_safe(s), indent=2, default=str))
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
            sp.add_argument(
                "--bench", action="append", default=[],
                help="a repo bench directory (bench.toml + goals/); repeatable. "
                "Without it the textkit benchmark runs.",
            )
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
