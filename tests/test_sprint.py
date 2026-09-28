"""Sprint mode (M9): slicing validation and the runner's four stateful-flow paths.

The runner is driven with a scripted slicer and a fake per-slice run (which
commits in the sprint worktree and writes the slice's state.json), so every path
runs against real git without a model call:

- forward: every slice completes, handover documents chain, held-out runs once;
- backtrack: a slice that escalates stops the sprint, later slices stay pending;
- resume / re-entry after failure: a rerun continues at the failed slice as a new
  attempt, never redoing completed slices;
- re-entry after completion: a rerun does nothing;
- STOP between slices and forwarded into a running slice; the up-front refusals.
"""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

import orchestrator.sprint as sprint_mod
from orchestrator.orchestrator import OrchestratorConfig
from orchestrator.sprint import SlicingError, SprintRecord, parse_slices, run_sprint
from orchestrator.state import CommitEntry, State, load_state, save_state

GIT = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
GOAL = "---\nverify: true\n---\n# Build the textkit extras\n\nDo three things.\n"


def _plan(n=3):
    return json.dumps(
        {
            "slices": [
                {"title": f"part {i}", "spec": f"do part {i}", "files": [f"p{i}.py"], "tests": [f"test_p{i}"]}
                for i in range(1, n + 1)
            ]
        }
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run([*GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "seed"], cwd=repo, check=True)
    return repo


def _cfg(tmp_path: Path, repo: Path, goal: str = GOAL, held_out: str | None = "true") -> OrchestratorConfig:
    (tmp_path / "goal.md").write_text(goal)
    (tmp_path / "p.md").write_text("persona")
    home = tmp_path / "home"
    return OrchestratorConfig(
        task_id="sp",
        goal_file=tmp_path / "goal.md",
        persona_file=tmp_path / "p.md",
        project_dir=repo,
        state_dir=home / "tasks" / "sp",
        orchestrator_home=home,
        repos_config=tmp_path / "repos.toml",
        held_out_override=held_out,
    )


class _Slicer:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def __call__(self, goal, files, max_slices, cwd=None):
        self.calls += 1
        self.cwd = cwd
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class _Slices:
    """Fake per-slice run: records the config, commits in the worktree, and
    writes the slice state with the scripted outcome for that call."""

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.cfgs: list[OrchestratorConfig] = []

    async def __call__(self, cfg):
        self.cfgs.append(cfg)
        status = self.outcomes.pop(0) if self.outcomes else "completed"
        n = len(self.cfgs)
        (cfg.project_dir / f"{cfg.task_id}.txt").write_text(f"{n}\n")
        subprocess.run([*GIT, "add", "-A"], cwd=cfg.project_dir, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", f"slice work {n}"], cwd=cfg.project_dir, check=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cfg.project_dir, capture_output=True, text=True).stdout.strip()
        st = State(task_id=cfg.task_id, goal=cfg.goal_file.read_text(), status=status)
        st.commits = [CommitEntry(sha=sha, message=f"slice work {n}")]
        st.exit_reason = "done" if status == "completed" else f"slice {n} {status}"
        st.last_worker_text = f"I finished piece {n}."
        save_state(cfg.state_dir / "state.json", st)


def _record(cfg) -> SprintRecord:
    return SprintRecord.model_validate_json((cfg.state_dir / "sprint.json").read_text())


# ---- slicing ----


def test_parse_slices_accepts_a_fenced_plan():
    assert [s.title for s in parse_slices("```json\n" + _plan(2) + "\n```")] == ["part 1", "part 2"]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"slices": []}),
        json.dumps({"parts": [1]}),
        json.dumps({"slices": [{"title": "t", "spec": "", "files": ["a"], "tests": ["b"]}]}),
        json.dumps({"slices": [{"title": "t", "spec": "s", "files": [], "tests": ["b"]}]}),
    ],
)
def test_parse_slices_refuses_unusable_plans(raw):
    with pytest.raises(SlicingError):
        parse_slices(raw)


def test_parse_slices_enforces_the_cap():
    with pytest.raises(SlicingError, match="cap"):
        parse_slices(_plan(9), max_slices=8)


# ---- forward ----


async def test_forward_every_slice_completes_and_handovers_chain(tmp_path):
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)
    slices = _Slices()
    handover = tmp_path / "vault" / "handover"
    result = await run_sprint(cfg, handover_dir=handover, slicer=_Slicer(_plan(3)), run_slice=slices)

    assert result.status == "completed"
    assert [s.status for s in result.slices] == ["completed"] * 3
    st = load_state(cfg.state_dir / "state.json")
    assert st.status == "completed" and st.iteration == 3
    # One worktree, slices in place, hidden tests deferred per slice.
    worktrees = {c.project_dir for c in slices.cfgs}
    assert len(worktrees) == 1 and repo not in worktrees
    assert all(c.held_out_deferred and not c.worktree_isolation for c in slices.cfgs)
    # Handover: per-slice files, a cumulative doc, and slice 2 saw slice 1's note.
    assert sorted(p.name for p in handover.iterdir()) == ["01-slice.md", "02-slice.md", "03-slice.md", "HANDOVER.md"]
    second_goal = slices.cfgs[1].goal_file.read_text()
    assert "Slice 2 of 3: part 2" in second_goal and "I finished piece 1." in second_goal
    assert second_goal.startswith("---\nverify: true\n---\n")
    # The held-out verifier ran once, on the finished tree.
    assert result.held_out is not None and result.held_out.status == "pass"
    # The branch carries the work; the clean worktree is gone.
    log = subprocess.run(["git", "log", "--format=%s", "orchestrator/sp"], cwd=repo, capture_output=True, text=True).stdout
    assert log.splitlines()[:3] == ["slice work 3", "slice work 2", "slice work 1"]
    assert not Path(result.worktree).exists()


# ---- backtrack, then re-entry after failure ----


async def test_escalated_slice_stops_the_sprint_and_a_rerun_retries_only_it(tmp_path):
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)
    slicer = _Slicer(_plan(3))
    first = _Slices(["completed", "escalated"])
    result = await run_sprint(cfg, slicer=slicer, run_slice=first)
    assert result.status == "escalated"
    assert "slice 2" in result.reason
    assert [s.status for s in result.slices] == ["completed", "escalated", "pending"]
    assert result.held_out is None  # never ran on an unfinished sprint
    assert load_state(cfg.state_dir / "state.json").status == "escalated"

    second = _Slices()
    result = await run_sprint(cfg, slicer=slicer, run_slice=second)
    assert result.status == "completed"
    assert slicer.calls == 1  # the plan is reused, never resliced
    assert [c.task_id for c in second.cfgs] == ["sp-slice-02-a2", "sp-slice-03-a1"]


async def test_resume_after_a_crash_mid_slice(tmp_path):
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)
    slicer = _Slicer(_plan(2))
    await run_sprint(cfg, slicer=slicer, run_slice=_Slices(["completed", "escalated"]))
    # Simulate a crash: the record says slice 2 is still running.
    rec = _record(cfg)
    rec.status = "running"
    rec.slices[1].status = "running"
    (cfg.state_dir / "sprint.json").write_text(rec.model_dump_json())
    again = _Slices()
    result = await run_sprint(cfg, slicer=slicer, run_slice=again)
    assert result.status == "completed"
    assert [c.task_id for c in again.cfgs] == ["sp-slice-02-a2"]


# ---- re-entry after completion ----


async def test_a_completed_sprint_started_again_does_nothing(tmp_path):
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)
    slicer = _Slicer(_plan(2))
    await run_sprint(cfg, slicer=slicer, run_slice=_Slices())
    again = _Slices()
    result = await run_sprint(cfg, slicer=slicer, run_slice=again)
    assert result.status == "completed"
    assert again.cfgs == [] and slicer.calls == 1


# ---- stop ----


async def test_stop_is_forwarded_into_the_running_slice_and_halts_the_sprint(tmp_path, monkeypatch):
    monkeypatch.setattr(sprint_mod, "_STOP_POLL_S", 0.05)
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)

    async def slice_that_gets_stopped(slice_cfg):
        (cfg.state_dir / "STOP").touch()  # the operator stops the sprint mid-slice
        for _ in range(100):
            if (slice_cfg.state_dir / "STOP").exists():
                break
            await asyncio.sleep(0.02)
        assert (slice_cfg.state_dir / "STOP").exists(), "STOP was not forwarded"
        save_state(slice_cfg.state_dir / "state.json", State(task_id="x", goal="g", status="stopped", exit_reason="kill switch"))

    result = await run_sprint(cfg, slicer=_Slicer(_plan(2)), run_slice=slice_that_gets_stopped)
    assert result.status == "stopped"
    assert [s.status for s in result.slices] == ["stopped", "pending"]


# ---- refusals and the final held-out ----


async def test_refuses_a_goal_without_verify(tmp_path):
    repo = _repo(tmp_path)
    slicer = _Slicer(_plan(1))
    result = await run_sprint(_cfg(tmp_path, repo, goal="# no frontmatter\n"), slicer=slicer, run_slice=_Slices())
    assert result.status == "stopped" and "verify" in result.reason
    assert slicer.calls == 0


async def test_refuses_a_non_claude_worker_without_held_out(tmp_path, monkeypatch):
    home = tmp_path / "cfg"
    home.mkdir()
    (home / "config.toml").write_text('[executors.worker]\nmodel_id = "mercury-2"\nprovider = "inception"\n')
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", str(home))
    repo = _repo(tmp_path)
    slicer = _Slicer(_plan(1))
    result = await run_sprint(_cfg(tmp_path, repo, held_out=None), slicer=slicer, run_slice=_Slices())
    assert result.status == "stopped" and "held-out verifier" in result.reason
    assert slicer.calls == 0


async def test_refuses_a_non_git_project(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    result = await run_sprint(_cfg(tmp_path, plain), slicer=_Slicer(_plan(1)), run_slice=_Slices())
    assert result.status == "failed"


async def test_malformed_slicing_fails_the_sprint(tmp_path):
    repo = _repo(tmp_path)
    result = await run_sprint(_cfg(tmp_path, repo), slicer=_Slicer("I would split it like so"), run_slice=_Slices())
    assert result.status == "failed" and "slicing failed" in result.reason


async def test_final_held_out_failure_escalates(tmp_path):
    repo = _repo(tmp_path)
    result = await run_sprint(_cfg(tmp_path, repo, held_out="false"), slicer=_Slicer(_plan(2)), run_slice=_Slices())
    assert result.status == "escalated"
    assert result.held_out is not None and result.held_out.status == "fail"
    assert "not fed back to a Worker" in result.reason


async def test_a_crashing_slicer_fails_the_sprint_instead_of_leaving_it_running(tmp_path):
    repo = _repo(tmp_path)
    cfg = _cfg(tmp_path, repo)
    result = await run_sprint(cfg, slicer=_Slicer(RuntimeError("max turns")), run_slice=_Slices())
    assert result.status == "failed" and "RuntimeError: max turns" in result.reason
    assert load_state(cfg.state_dir / "state.json").status == "failed"


async def test_the_slicer_reads_the_sprint_worktree(tmp_path):
    repo = _repo(tmp_path)
    slicer = _Slicer(_plan(1))
    result = await run_sprint(_cfg(tmp_path, repo), slicer=slicer, run_slice=_Slices())
    assert slicer.cwd is not None and str(slicer.cwd) == result.worktree
