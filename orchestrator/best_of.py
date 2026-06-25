"""Best-of-N: run N independent attempts on one goal, select by the HELD-OUT
verifier ONLY (Wave 2 leaf L8).

This is a THIN ORCHESTRATION LAYER over the existing single-attempt machinery
(``run_orchestrator`` + worktree-per-attempt isolation + ``held_out.py``). It is
NOT a new execution engine and does NOT touch the Worker / Decision-Proxy /
Marlin-Proxy loop. It calls ``run_orchestrator`` N times, each in its OWN git
worktree / branch (``orchestrator/<task-id>-attempt-<k>``), collects each
attempt's terminal ``State``, and picks a winner.

The whole point is that selection cannot be reward-hacked. The in-tree ``verify``
gate is what the Worker SEES and can game, so it can NEVER be the selection
metric. The ONLY selection signal is the held-out verifier (an operator-sourced
test set on a path the Worker cannot write, resolved from the repo registry by
the real git remote, or supplied ad-hoc via ``--held-out``). Among attempts that
reached ``completed`` AND whose held-out gate PASSED, the winner is the one with
the LOWEST ``time_to_verified_ms`` (the cumulative wall-clock its iterations
spent, the north-star "time_to_verified_result" metric), tie-broken by attempt
index for determinism.

Two hard safety properties:

1. **No held-out, no best-of-N.** best-of-N ships ONLY because a trustworthy
   out-of-reach signal exists. Without one, "best of N" just amplifies the most
   convincing reward-hack. So if NO held-out is resolvable (no registry
   ``held_out_verify`` and no ``--held-out`` override), ``run_best_of_n`` REFUSES
   up front (escalates) and runs ZERO attempts. A safety property, not an edge
   case.
2. **A held-out fail is NEVER a Worker retry.** ``run_orchestrator`` already
   escalates (never retries) on a held-out fail, and this layer only READS each
   attempt's terminal state. A failed attempt is simply excluded from selection;
   nothing is fed back to any Worker. Feeding the hidden result back would teach
   to the held-out set and defeat the point.

Sequential attempts are acceptable for this first slice: attempts run one after
another, each fully isolated in its own worktree, so they never collide. The
per-run token cap and the fleet-wide daily cap are honored per attempt (each
attempt is a full ``run_orchestrator`` run with the same caps and shares the
``orchestrator_home`` usage ledger, so the daily budget sums across the cohort).
Parallel attempts are a later optimization, not a correctness change.

A cohort/selection EVENT (L7 ``events.py``) is intentionally NOT forced here:
``events.py`` projects a SINGLE ``State`` into a stream, while a cohort spans N
states. The typed ``CohortResult`` (its own ``types/cohort.d.ts`` contract,
written to ``<state_dir>/cohort.json``) is the board-facing artifact, and a
cohort-level event projection is left as a clean future seam.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from rich.console import Console

from orchestrator.repo_registry import resolve_repo_policy
from orchestrator.state import State, TaskStatus, VerifyStatus, load_state
from orchestrator.worktree import is_git_repo, worktree_branch

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime SDK import
    from orchestrator.orchestrator import OrchestratorConfig

logger = logging.getLogger(__name__)
console = Console()


# The cohort's own terminal status. `completed` = a held-out-green winner was
# selected; `escalated` = no winner (zero held-out-green, or refused because no
# held-out is resolvable); `failed` = a structural failure (not a git repo, or a
# malformed registry) before/while running the cohort.
CohortStatus = TaskStatus  # reuse the same vocabulary; cohort uses completed/escalated/failed


class CohortAttempt(BaseModel):
    """One attempt's board-facing record. ``held_out`` is the attempt's held-out
    gate result (``pass`` is the ONLY value that makes an attempt selectable);
    ``time_to_verified_ms`` is the cumulative wall-clock its iterations spent
    (the selection metric among held-out-green attempts, lower = better);
    ``selected`` marks the cohort winner. ``status`` and ``exit_reason`` mirror
    the attempt's terminal State for provenance."""

    attempt_index: int
    task_id: str
    branch: str
    status: TaskStatus
    held_out: VerifyStatus | None = None
    time_to_verified_ms: int = 0
    selected: bool = False
    exit_reason: str | None = None


class CohortResult(BaseModel):
    """The typed best-of-N cohort record a board reads. ``selected_branch`` is the
    winner's branch, or ``None`` on an escalation (zero held-out-green or a
    refusal). ``status`` is the cohort's terminal status and ``reason`` explains
    the outcome. ``attempts`` preserves every attempt's record in launch order."""

    task_id: str
    n: int
    status: CohortStatus
    selected_branch: str | None = None
    reason: str = ""
    attempts: list[CohortAttempt] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def time_to_verified_ms(state: State) -> int:
    """The attempt's cumulative wall-clock: the sum of every iteration's
    ``worker_ms + proxy_ms``. This is the "time_to_verified_result" north-star
    metric, the antidote to "fast tok/s = cheaper": an attempt that burned extra
    verify-fix loops accrues more iteration time and so loses to one that landed
    held-out-green with less work. Deterministic and computable from the terminal
    State alone; the ONLY tie among held-out-green attempts is broken by it (then
    by attempt index)."""
    return sum(u.worker_ms + u.proxy_ms for u in state.usage)


def _build_attempt_cfg(cfg: "OrchestratorConfig", index: int) -> "OrchestratorConfig":
    """Derive an isolated per-attempt config from the base config.

    Each attempt gets a distinct ``task_id`` (``<base>-attempt-<k>``), its own
    state dir + run.log (siblings of the base task dir), and FORCED worktree
    isolation so ``run_orchestrator`` runs it on its own branch
    ``orchestrator/<base>-attempt-<k>`` in its own tree, never colliding with
    another attempt. Everything else (caps, auth, persona, held-out override,
    confirm-stakes, the shared ``orchestrator_home`` ledger) is inherited from
    the base config unchanged, so each attempt is a full, faithful single run.
    """
    attempt_task_id = f"{cfg.task_id}-attempt-{index}"
    attempt_state_dir = cfg.state_dir.parent / attempt_task_id
    return dataclasses.replace(
        cfg,
        task_id=attempt_task_id,
        state_dir=attempt_state_dir,
        log_path=attempt_state_dir / "run.log",
        # Per-attempt isolation is mandatory: N attempts must never edit the same
        # tree. run_orchestrator creates + manages the worktree on the branch.
        worktree_isolation=True,
    )


async def _run_attempt(attempt_cfg: "OrchestratorConfig") -> State:
    """Run ONE attempt via the existing single-attempt path and return its
    terminal ``State``.

    The Worker / Proxy loop is reused verbatim (lazy import keeps best_of.py
    SDK-free for the typed-contract generator). This is the single seam tests
    mock so the suite never spawns a real Worker.
    """
    from orchestrator.orchestrator import run_orchestrator

    await run_orchestrator(attempt_cfg)
    return load_state(attempt_cfg.state_dir / "state.json")


def _save_cohort(state_dir: Path, result: CohortResult) -> None:
    """Atomically write the cohort record to ``<state_dir>/cohort.json`` (tmp +
    rename), so a board has a typed artifact for the run and a partial write can
    never be read."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "cohort.json"
    serialized = result.model_dump_json(indent=2)
    fd, tmp_path_str = tempfile.mkstemp(prefix="cohort.json.", suffix=".tmp", dir=str(state_dir))
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(serialized)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _select_winner(attempts: list[CohortAttempt]) -> CohortAttempt | None:
    """Pick the cohort winner using the held-out verifier ONLY.

    Eligible = reached ``completed`` AND held-out gate PASSED. The winner is the
    eligible attempt with the LOWEST ``time_to_verified_ms``, tie-broken by
    ``attempt_index`` for full determinism. NEVER consults ``last_verify`` (the
    Worker-visible, gameable signal). Returns ``None`` when no attempt is
    held-out-green (the caller then escalates without selecting).
    """
    eligible = [a for a in attempts if a.status == "completed" and a.held_out == "pass"]
    if not eligible:
        return None
    return min(eligible, key=lambda a: (a.time_to_verified_ms, a.attempt_index))


async def run_best_of_n(cfg: "OrchestratorConfig", n: int) -> CohortResult:
    """Run ``n`` isolated attempts of ``cfg``'s goal and select the held-out-green
    winner with the lowest time_to_verified.

    REFUSES up front (runs ZERO attempts) when best-of-N cannot be done safely:
    when the project is not a git repo (no per-attempt isolation possible), or
    when no held-out is resolvable (no registry ``held_out_verify`` and no
    ``--held-out`` override). The held-out refusal is the load-bearing safety
    property: without a trustworthy out-of-reach signal there is nothing to
    select on but the gameable in-tree verify, so best-of-N would just amplify
    the most convincing reward-hack.

    Returns the typed ``CohortResult`` (also written to ``<state_dir>/cohort.json``).
    """
    n = max(1, int(n))
    state_dir = cfg.state_dir

    def _refuse(status: CohortStatus, reason: str) -> CohortResult:
        result = CohortResult(task_id=cfg.task_id, n=n, status=status, reason=reason)
        _save_cohort(state_dir, result)
        return result

    # Gate 1: per-attempt isolation needs git worktrees. A non-git project cannot
    # isolate N attempts, so best-of-N refuses rather than running them in place
    # where they would collide.
    if not is_git_repo(cfg.project_dir):
        reason = (
            "best-of-N requires a git repo for per-attempt worktree isolation; "
            f"{cfg.project_dir} is not a git repo"
        )
        console.print(f"[bold red]best-of-N refused:[/bold red] {reason}")
        return _refuse("failed", reason)

    # Gate 2 (the heart of the gate): a held-out verifier MUST be resolvable, or
    # there is no reward-hack-proof signal to select on. Resolve the operator
    # policy by the REAL git remote (un-fakeable by the goal file); a malformed
    # registry fails loud.
    try:
        policy = resolve_repo_policy(cfg.project_dir, cfg.repos_config)
    except ValueError as e:
        reason = f"repo registry error: {e}"
        console.print(f"[bold red]best-of-N failed:[/bold red] {reason}")
        return _refuse("failed", reason)

    held_out_resolvable = bool(policy.held_out_verify) or bool(cfg.held_out_override)
    if not held_out_resolvable:
        reason = (
            "best-of-N requires a held-out verifier: selection is held-out-certified, "
            "never by the Worker-visible in-tree verify. No registry held_out_verify "
            "for this repo and no --held-out override. Refusing (zero attempts run)."
        )
        console.print(f"[bold red]best-of-N refused:[/bold red] {reason}")
        return _refuse("escalated", reason)

    console.print(
        f"[bold cyan]best-of-N:[/bold cyan] running {n} isolated attempt(s) of "
        f"task {cfg.task_id}; selection is HELD-OUT-certified (in-tree verify never selects)"
    )

    attempts: list[CohortAttempt] = []
    for k in range(n):
        attempt_cfg = _build_attempt_cfg(cfg, k)
        branch = worktree_branch(attempt_cfg.task_id)
        console.print(
            f"[cyan]best-of-N attempt {k + 1}/{n}:[/cyan] {attempt_cfg.task_id} "
            f"(branch {branch})"
        )
        state = await _run_attempt(attempt_cfg)
        held = state.last_held_out.status if state.last_held_out is not None else None
        ttv = time_to_verified_ms(state)
        attempts.append(
            CohortAttempt(
                attempt_index=k,
                task_id=attempt_cfg.task_id,
                branch=branch,
                status=state.status,
                held_out=held,
                time_to_verified_ms=ttv,
                exit_reason=state.exit_reason,
            )
        )
        console.print(
            f"[dim]  -> status={state.status} held_out={held or 'n/a'} "
            f"time_to_verified_ms={ttv}[/dim]"
        )

    winner = _select_winner(attempts)
    if winner is None:
        green = sum(1 for a in attempts if a.held_out == "pass")
        reason = (
            f"no attempt was held-out-green ({n} attempt(s); held-out passes: {green}). "
            "best-of-N does not select by the Worker-visible in-tree verify, so the "
            "cohort escalates rather than blessing an unverified green."
        )
        console.print(f"[bold red]best-of-N: ESCALATE[/bold red] {reason}")
        result = CohortResult(
            task_id=cfg.task_id,
            n=n,
            status="escalated",
            selected_branch=None,
            reason=reason,
            attempts=attempts,
        )
        _save_cohort(state_dir, result)
        return result

    winner.selected = True
    reason = (
        f"selected held-out-green attempt {winner.attempt_index} (branch "
        f"{winner.branch}) with the lowest time_to_verified_ms="
        f"{winner.time_to_verified_ms}"
    )
    console.print(f"[bold green]best-of-N: SELECTED[/bold green] {reason}")
    result = CohortResult(
        task_id=cfg.task_id,
        n=n,
        status="completed",
        selected_branch=winner.branch,
        reason=reason,
        attempts=attempts,
    )
    _save_cohort(state_dir, result)
    return result
