"""Sprint mode: the M9 "sprint worker" mechanism (Agentic OS design section 6.3).

A sprint takes one larger goal and runs it as a sequence of small, file-scoped
slices, each a full orchestrator run with a fresh Worker session:

1. **Slicing, once.** A single-shot Claude call (the ``planner`` role, which
   must be Claude like both Proxies) turns the goal into at most
   ``MAX_SLICES`` slices: title, spec, files, the tests it adds. Malformed
   output fails the sprint; it is never parsed best-effort.
2. **One worktree, slices in place.** The sprint owns a single worktree on
   ``orchestrator/<task-id>``; every slice runs inside it, so later slices build
   on earlier commits. Each slice keeps the goal's in-tree ``verify`` as its
   gate and the Decision Proxy on every iteration.
3. **Handover document.** After each slice the runner (not the Worker, whose
   tools are confined to the work dir) writes a compact markdown document from
   the slice's state and the Worker's last message, into ``--handover-dir``.
   The cumulative document is injected into the next slice's goal.
4. **Token watcher.** Within a slice, the loop's context handover (threshold
   capped at 70 percent of the model window) refreshes a long session.
5. **Hidden tests once.** Slices resolve the held-out verifier (so the E4 gate
   admits a non-Claude Worker) but defer running it; the sprint runs it once on
   the finished tree. A failure escalates and is never fed back to a Worker.

State: a normal ``state.json`` in the sprint's task dir (status, ``iteration`` =
slices completed, ``exit_reason``), so anything that watches a run watches a
sprint; per-slice detail in ``sprint.json`` (typed, ``types/sprint.d.ts``).
``STOP`` in the sprint's task dir halts between slices and is forwarded into the
running slice. A restarted sprint resumes at the first slice not completed; a
failed or stopped slice is retried as a fresh attempt; a completed sprint started
again does nothing.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from orchestrator.executor import resolve_executor
from orchestrator.handover import HANDOVER_FILE
from orchestrator.parse import parse_frontmatter
from orchestrator.repo_registry import resolve_repo_policy
from orchestrator.state import HeldOutRecord, State, TaskStatus, load_state, save_state
from orchestrator.verify import load_verify_config, run_verify
from orchestrator.worktree import (
    add_worktree,
    default_worktree_path,
    is_git_repo,
    remove_worktree,
    worktree_branch,
)

console = Console()

MAX_SLICES = 8
SPRINT_FILE = "sprint.json"
_STOP_POLL_S = 2.0

SliceStatus = Literal["pending", "running", "completed", "escalated", "stopped", "failed"]


class SlicePlan(BaseModel):
    """One slice as the slicer proposes it."""

    title: str = Field(min_length=1)
    spec: str = Field(min_length=1)
    files: list[str] = Field(min_length=1)
    tests: list[str] = Field(min_length=1)


class SliceRecord(BaseModel):
    index: int
    plan: SlicePlan
    status: SliceStatus = "pending"
    attempts: int = 0
    task_id: str | None = None
    exit_reason: str | None = None
    commits: list[str] = []
    handover_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SprintRecord(BaseModel):
    """The typed per-slice record of a sprint (``sprint.json``), what a board reads."""

    task_id: str
    status: TaskStatus = "running"
    reason: str = ""
    branch: str | None = None
    worktree: str | None = None
    handover_dir: str | None = None
    slices: list[SliceRecord] = []
    held_out: HeldOutRecord | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlicingError(ValueError):
    """The slicer's output was not a usable plan."""


# ---- slicing ----

SLICER_SYSTEM_PROMPT = """\
You split a software goal into an ordered sequence of small, file-scoped slices
for autonomous coding Workers. Each slice is done by a fresh Worker that sees only
its slice spec, the files you list and a handover note from earlier slices.

Rules:
- Each slice must leave the test suite green on its own: it adds the tests for
  what it builds, and never depends on a later slice.
- Keep slices small (one feature, fix or refactor step each) and name the files
  each one touches. Order them so each builds on the previous ones.
- Use as few slices as the goal needs, never more than {max_slices}.

Reply with ONLY a JSON object, no prose, no code fence:
{{"slices": [{{"title": "...", "spec": "...", "files": ["..."], "tests": ["..."]}}]}}
`spec` is what the Worker must do, precise enough to implement without the
original goal; `tests` names the test cases the slice adds.
"""


def parse_slices(raw: str, *, max_slices: int = MAX_SLICES) -> list[SlicePlan]:
    """Validate the slicer's reply. Anything but a well-formed, non-empty plan
    within the cap raises SlicingError; there is no best-effort parse."""
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SlicingError(f"slicer reply is not JSON: {raw[:200]!r}") from e
    items = data.get("slices") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise SlicingError("slicer reply has no non-empty 'slices' list")
    if len(items) > max_slices:
        raise SlicingError(f"slicer proposed {len(items)} slices; the cap is {max_slices}")
    try:
        return [SlicePlan.model_validate(item) for item in items]
    except ValidationError as e:
        raise SlicingError(f"slicer reply has an invalid slice: {e}") from e


async def claude_slicer(goal: str, repo_files: list[str], max_slices: int, cwd: Path | None = None) -> str:
    """The production slicer call: a read-only Claude session in the style of
    the Decision Proxy (no hooks; Read, Grep and Glob inside the sprint's
    worktree, so it can look at the code it is slicing)."""
    from claude_agent_sdk import ClaudeAgentOptions, query

    from orchestrator.transcript import extract_text

    prompt = (
        "Goal to split:\n\n" + goal + "\n\nFiles in the repository:\n" + "\n".join(repo_files[:400])
    )
    options = ClaudeAgentOptions(
        system_prompt=SLICER_SYSTEM_PROMPT.format(max_slices=max_slices),
        setting_sources=[],
        allowed_tools=["Read", "Grep", "Glob"],
        disallowed_tools=["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"],
        cwd=str(cwd) if cwd else None,
    )
    chunks: list[str] = []
    async for msg in query(prompt=prompt, options=options):
        text = extract_text(msg)
        if text:
            chunks.append(text)
    return "".join(chunks)


Slicer = Callable[..., Awaitable[str]]


# ---- the handover document ----


def compose_slice_handover(record: SliceRecord, slice_state: State) -> str:
    """A compact markdown note about one finished slice, built from machine state
    plus the Worker's own last message."""
    lines = [f"## Slice {record.index + 1}: {record.plan.title}", ""]
    if slice_state.commits:
        lines.append("Commits:")
        lines += [f"- `{c.sha[:12]}` {c.message}".rstrip() for c in slice_state.commits if c.sha]
    files = sorted({f.path for f in slice_state.files_touched})
    if files:
        lines.append("Files changed: " + ", ".join(f"`{f}`" for f in files))
    if slice_state.decisions:
        lines.append("Decisions:")
        lines += [f"- {d.question}: {d.answer}" for d in slice_state.decisions]
    notes = [*slice_state.open_threads, *slice_state.assumptions_made]
    if notes:
        lines.append("Open points and assumptions:")
        lines += [f"- {n}" for n in notes]
    if slice_state.last_worker_text.strip():
        lines += ["", "The Worker's closing note:", "", slice_state.last_worker_text.strip()[-1500:]]
    return "\n".join(lines) + "\n"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (the raw frontmatter block including its --- lines, the body)."""
    m = re.match(r"\A(---\n.*?\n---\n)(.*)\Z", text, flags=re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def build_slice_goal(goal_text: str, sprint: SprintRecord, record: SliceRecord, handover: str) -> str:
    """The goal file for one slice: the sprint goal's frontmatter (its verify is
    the slice's gate), the slice spec, and the handover from earlier slices."""
    frontmatter, body = _split_frontmatter(goal_text)
    title = next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.strip()), "the sprint goal")
    plan = record.plan
    parts = [
        frontmatter + f"# Slice {record.index + 1} of {len(sprint.slices)}: {plan.title}",
        f"This is one slice of a larger sprint (overall goal: {title}). Do ONLY this slice; "
        "later slices are handled by other Workers. Leave the test suite green, commit your "
        "work with git, and stop.",
        "## What to do\n\n" + plan.spec,
        "## Files\n\n" + "\n".join(f"- `{f}`" for f in plan.files),
        "## Tests to add\n\n" + "\n".join(f"- {t}" for t in plan.tests),
    ]
    if handover.strip():
        parts.append("## Handover from earlier slices\n\n" + handover.strip())
    return "\n\n".join(parts) + "\n"


# ---- the runner ----


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_sprint(path: Path) -> SprintRecord | None:
    return SprintRecord.model_validate_json(path.read_text()) if path.exists() else None


def _save_sprint(path: Path, sprint: SprintRecord) -> None:
    sprint.updated_at = _now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(sprint.model_dump_json(indent=2))
    tmp.replace(path)


def _repo_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    return out.stdout.splitlines() if out.returncode == 0 else []


def _remove_untracked_handover(root: Path) -> None:
    """The in-slice context handover asks the Worker for a HANDOVER.md at the
    repo root; never let it leak into the next slice as an untracked file."""
    doc = root / HANDOVER_FILE
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", HANDOVER_FILE], cwd=root, capture_output=True
    ).returncode == 0
    if doc.exists() and not tracked:
        doc.unlink()


async def _forward_stop(sprint_stop: Path, slice_dir: Path, done: asyncio.Event) -> None:
    """Mirror the sprint's STOP into the running slice's task dir."""
    while not done.is_set():
        if sprint_stop.exists():
            slice_dir.mkdir(parents=True, exist_ok=True)
            (slice_dir / "STOP").touch()
            return
        try:
            await asyncio.wait_for(done.wait(), timeout=_STOP_POLL_S)
        except asyncio.TimeoutError:
            pass


async def run_sprint(
    cfg,
    *,
    handover_dir: Path | None = None,
    max_slices: int = MAX_SLICES,
    slicer: Slicer | None = None,
    run_slice: Callable[[object], Awaitable[None]] | None = None,
) -> SprintRecord:
    """Run (or resume) the sprint described by ``cfg`` (an ``OrchestratorConfig``
    whose ``goal_file`` is the sprint goal). Returns the final ``SprintRecord``."""
    from orchestrator.orchestrator import _initialize_state, run_orchestrator

    slicer = slicer or claude_slicer
    run_slice = run_slice or run_orchestrator
    _initialize_state(cfg)
    state_path = cfg.state_dir / "state.json"
    sprint_path = cfg.state_dir / SPRINT_FILE
    stop_file = cfg.state_dir / "STOP"
    handover_dir = Path(handover_dir) if handover_dir else cfg.state_dir / "handover"
    goal_text = cfg.goal_file.read_text()

    def finish(sprint: SprintRecord, status: TaskStatus, reason: str) -> SprintRecord:
        sprint.status, sprint.reason = status, reason
        _save_sprint(sprint_path, sprint)
        st = load_state(state_path)
        st.status, st.exit_reason = status, reason
        st.iteration = sum(1 for s in sprint.slices if s.status == "completed")
        save_state(state_path, st)
        color = "green" if status == "completed" else "red"
        console.print(f"[bold {color}]sprint {status}:[/bold {color}] {reason}")
        return sprint

    sprint = _load_sprint(sprint_path) or SprintRecord(task_id=cfg.task_id)
    if sprint.status == "completed":
        console.print(f"[yellow]sprint {cfg.task_id} already completed; nothing to do[/yellow]")
        return sprint
    if sprint.status in ("escalated", "stopped", "failed"):
        console.print(f"[yellow]re-entering sprint {cfg.task_id} after {sprint.status}: {sprint.reason}[/yellow]")
    if sprint.status == "stopped":
        stop_file.unlink(missing_ok=True)  # the operator restarted a stopped sprint
    sprint.status, sprint.reason = "running", ""
    st = load_state(state_path)
    st.status, st.exit_reason = "running", None
    save_state(state_path, st)
    _save_sprint(sprint_path, sprint)

    # Gates before any model call: a git project, an in-tree verify for the
    # slices, and (for a non-Claude Worker) a held-out verifier.
    if not is_git_repo(cfg.project_dir):
        return finish(sprint, "failed", f"sprint needs a git repository: {cfg.project_dir}")
    if load_verify_config(parse_frontmatter(goal_text)).command is None:
        return finish(sprint, "stopped", "sprint refused: the goal has no `verify` command, and every slice needs one as its gate")
    try:
        policy = resolve_repo_policy(cfg.project_dir, cfg.repos_config)
        worker = resolve_executor("worker")
        planner = resolve_executor("planner")
    except ValueError as e:
        return finish(sprint, "failed", f"configuration error: {e}")
    held_out = policy.held_out_verify or cfg.held_out_override
    if not worker.is_claude and not held_out:
        return finish(
            sprint,
            "stopped",
            f"sprint refused: worker provider {worker.provider!r} needs a held-out verifier "
            "(repo registry held_out_verify or --held-out)",
        )
    if not planner.is_claude:
        return finish(sprint, "stopped", "sprint refused: the planner (slicer) role must stay Claude")

    # One worktree for the whole sprint.
    branch = worktree_branch(cfg.task_id)
    worktree = Path(sprint.worktree) if sprint.worktree else default_worktree_path(cfg.project_dir, cfg.task_id)
    try:
        add_worktree(cfg.project_dir, worktree, branch)
    except RuntimeError as e:
        return finish(sprint, "failed", f"worktree: {e}")
    sprint.branch, sprint.worktree, sprint.handover_dir = branch, str(worktree), str(handover_dir)
    handover_dir.mkdir(parents=True, exist_ok=True)

    if not sprint.slices:
        console.print("[cyan]sprint: slicing the goal (Claude)[/cyan]")
        try:
            raw = await slicer(goal_text, _repo_files(worktree), max_slices, cwd=worktree)
            plans = parse_slices(raw, max_slices=max_slices)
        except SlicingError as e:
            return finish(sprint, "failed", f"slicing failed: {e}")
        except Exception as e:  # the model call itself failed: end visibly, never stay "running"
            return finish(sprint, "failed", f"slicing failed: {type(e).__name__}: {e}")
        sprint.slices = [SliceRecord(index=i, plan=p) for i, p in enumerate(plans)]
        console.print(f"[cyan]sprint: {len(plans)} slice(s)[/cyan]")
    _save_sprint(sprint_path, sprint)

    cumulative = handover_dir / HANDOVER_FILE
    for record in sprint.slices:
        if record.status == "completed":
            continue
        if stop_file.exists():
            return finish(sprint, "stopped", f"stopped before slice {record.index + 1}")
        record.attempts += 1
        record.status = "running"
        record.task_id = f"{cfg.task_id}-slice-{record.index + 1:02d}-a{record.attempts}"
        record.started_at, record.finished_at, record.exit_reason = _now(), None, None
        _save_sprint(sprint_path, sprint)

        slice_dir = cfg.state_dir.parent / record.task_id
        slice_dir.mkdir(parents=True, exist_ok=True)
        goal_file = slice_dir / "goal.md"
        goal_file.write_text(
            build_slice_goal(goal_text, sprint, record, cumulative.read_text() if cumulative.exists() else "")
        )
        slice_cfg = dataclasses.replace(
            cfg,
            task_id=record.task_id,
            goal_file=goal_file,
            state_dir=slice_dir,
            log_path=slice_dir / "run.log",
            project_dir=worktree,
            worktree_isolation=False,
            held_out_override=cfg.held_out_override,
            held_out_deferred=True,
        )
        console.print(f"[bold cyan]sprint: slice {record.index + 1}/{len(sprint.slices)}[/bold cyan] {record.plan.title}")
        done = asyncio.Event()
        watcher = asyncio.create_task(_forward_stop(stop_file, slice_dir, done))
        try:
            await run_slice(slice_cfg)
        except Exception as e:
            record.status, record.finished_at = "failed", _now()
            record.exit_reason = f"{type(e).__name__}: {e}"
            result = finish(
                sprint,
                "failed",
                f"slice {record.index + 1} ({record.plan.title}) raised {type(e).__name__}: {e}",
            )
            try:
                _remove_untracked_handover(worktree)
            except Exception as cleanup_error:
                console.print(f"[yellow]handover cleanup failed: {cleanup_error}[/yellow]")
            return result
        finally:
            done.set()
            await watcher
        _remove_untracked_handover(worktree)

        slice_state = load_state(slice_dir / "state.json")
        record.finished_at = _now()
        record.exit_reason = slice_state.exit_reason
        record.commits = [c.sha for c in slice_state.commits if c.sha]
        if slice_state.status != "completed":
            record.status = slice_state.status if slice_state.status in ("escalated", "stopped", "failed") else "failed"
            sprint_status: TaskStatus = "stopped" if record.status == "stopped" else "escalated"
            return finish(
                sprint,
                sprint_status,
                f"slice {record.index + 1} ({record.plan.title}) ended {slice_state.status}: "
                f"{slice_state.exit_reason or 'no reason recorded'}",
            )
        record.status = "completed"
        note = compose_slice_handover(record, slice_state)
        per_slice = handover_dir / f"{record.index + 1:02d}-slice.md"
        per_slice.write_text(note)
        with cumulative.open("a", encoding="utf-8") as f:
            f.write(note + "\n")
        record.handover_path = str(per_slice)
        st = load_state(state_path)
        st.iteration = sum(1 for s in sprint.slices if s.status == "completed")
        save_state(state_path, st)
        _save_sprint(sprint_path, sprint)

    # The hidden tests, once, on the finished tree.
    verify_cfg = load_verify_config(parse_frontmatter(goal_text))
    if held_out:
        console.print("[bold]sprint: running the held-out verifier on the finished tree[/bold]")
        outcome = await run_verify(held_out, worktree, verify_cfg.timeout_s)
        sprint.held_out = HeldOutRecord(
            iteration=len(sprint.slices),
            command=outcome.command,
            status=outcome.status,
            exit_code=outcome.exit_code,
            tail=outcome.tail,
        )
        if outcome.status != "pass":
            return finish(
                sprint,
                "escalated",
                f"held-out verifier {outcome.status} on the finished sprint (exit {outcome.exit_code}); "
                "the slices passed their in-tree verify, so this is the reward-hack fingerprint or a "
                "gap between slices, and it is not fed back to a Worker",
            )
    result = finish(sprint, "completed", f"{len(sprint.slices)} slice(s) completed" + ("; held-out passed" if held_out else "; no held-out verifier configured"))
    removed, msg = remove_worktree(cfg.project_dir, worktree)
    if removed:
        console.print(f"[dim]worktree removed; work is on branch {branch}[/dim]")
    else:
        console.print(f"[yellow]worktree kept: {msg}[/yellow]")
    return result
