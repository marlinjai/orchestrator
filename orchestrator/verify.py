"""In-loop verify gate: run a project's own verify command before accepting a
Worker's `stop` as `completed`.

The Decision Proxy can return `stop` on the Worker's unverified claim, and
reconcile only confirms that git changed, not that the build passes. So a Worker
can declare done on a red build and the Proxy accepts it. This module closes
that hole: on a stop-candidate it runs a deterministic, project-declared verify
command (for example `pnpm test && pnpm build && tsc --noEmit && pnpm lint`) in
the project worktree and turns the exit code into a gate decision:

- pass          -> accept `completed`.
- fail          -> feed the failure back to the Worker (evaluator-optimizer) up
                   to `fix_cap` consecutive failures, then escalate.
- misconfigured -> escalate now. Covers a denylisted command, a timeout, or a
                   process that could not start: the gate got no clean pass/fail
                   signal, so a human decides rather than the loop guessing.

The gate is deliberately domain-agnostic: it runs a shell command and reads the
exit code. Project-specific critics (for example a values-only schema round-trip)
are expressed by appending their script to the goal's `verify` command, never by
teaching the orchestrator about any project's data model. There is no hardcoded
default command: the orchestrator is project-agnostic and a pnpm default would
always fail on a non-JS project, so a goal that wants the gate declares it.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from orchestrator.guardrails import bash_allowed


DEFAULT_FIX_CAP = 2
DEFAULT_TIMEOUT_S = 1200.0
_TAIL_CHARS = 4000


VerifyStatus = Literal["pass", "fail", "misconfigured"]
GateAction = Literal["complete", "retry", "escalate"]


@dataclass
class VerifyConfig:
    command: str | None = None
    fix_cap: int = DEFAULT_FIX_CAP
    timeout_s: float = DEFAULT_TIMEOUT_S


@dataclass
class VerifyOutcome:
    status: VerifyStatus
    exit_code: int | None
    tail: str
    command: str


@dataclass
class GateDecision:
    action: GateAction
    attempts: int
    exit_reason: str | None = None
    next_message: str | None = None


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def load_verify_config(frontmatter: dict) -> VerifyConfig:
    """Read the verify-gate config from goal-file frontmatter.

    Recognized keys:
      verify            the shell command run before accepting completion.
      verify_fix_cap    consecutive verify failures tolerated before escalate.
      verify_timeout_s  per-run wall-clock timeout, in seconds.

    Absent or blank `verify` yields command=None, which skips the gate (the
    caller logs a warning). fix_cap is floored at 1 so a misconfigured 0 still
    escalates on the first failure rather than looping forever.
    """
    raw_cmd = frontmatter.get("verify")
    command = raw_cmd.strip() if isinstance(raw_cmd, str) and raw_cmd.strip() else None
    return VerifyConfig(
        command=command,
        fix_cap=max(1, _coerce_int(frontmatter.get("verify_fix_cap"), DEFAULT_FIX_CAP)),
        timeout_s=_coerce_float(frontmatter.get("verify_timeout_s"), DEFAULT_TIMEOUT_S),
    )


def _tail(text: str, limit: int = _TAIL_CHARS) -> str:
    text = text.rstrip()
    if len(text) <= limit:
        return text
    return "...(truncated)...\n" + text[-limit:]


async def run_verify(command: str, project_dir: Path, timeout_s: float) -> VerifyOutcome:
    """Run `command` in `project_dir` and classify the result.

    A command that hits the bash denylist (gh pr merge, pnpm publish, infisical
    run, terraform apply, ...) is refused as `misconfigured`, so a goal file
    cannot smuggle a forbidden action through the verify path. A timeout or a
    process that cannot start is also `misconfigured`: the gate got no clean
    pass/fail signal, so escalate rather than guess. Runs via a shell so the
    usual `a && b && c` verify chains work; stderr is merged into stdout so the
    failure tail carries the actual error.
    """
    allowed, reason = bash_allowed(command)
    if not allowed:
        return VerifyOutcome(
            status="misconfigured",
            exit_code=None,
            tail=f"verify command refused by denylist: {reason}",
            command=command,
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as e:
        return VerifyOutcome(
            status="misconfigured",
            exit_code=None,
            tail=f"verify command could not start: {e}",
            command=command,
        )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.communicate()
        except Exception:
            pass
        return VerifyOutcome(
            status="misconfigured",
            exit_code=None,
            tail=f"verify command timed out after {timeout_s:.0f}s",
            command=command,
        )

    output = stdout.decode("utf-8", errors="replace") if stdout else ""
    code = proc.returncode if proc.returncode is not None else -1
    return VerifyOutcome(
        status="pass" if code == 0 else "fail",
        exit_code=code,
        tail=_tail(output),
        command=command,
    )


def decide_after_verify(
    *, outcome: VerifyOutcome, prior_attempts: int, fix_cap: int
) -> GateDecision:
    """Pure decision: from a verify outcome and the prior consecutive-failure
    count, decide complete / retry / escalate. No I/O, no LLM, so it is fully
    unit-testable. The caller persists `attempts` back onto state.

    A pass resets the failure count to 0. A misconfigured outcome escalates and
    leaves the count untouched. A fail increments the count; once it reaches the
    cap it escalates, otherwise it returns a retry whose `next_message` carries
    the failure back to the Worker.
    """
    if outcome.status == "pass":
        return GateDecision(action="complete", attempts=0)

    if outcome.status == "misconfigured":
        return GateDecision(
            action="escalate",
            attempts=prior_attempts,
            exit_reason=f"verify misconfigured: {outcome.tail}",
        )

    attempts = prior_attempts + 1
    if attempts >= fix_cap:
        return GateDecision(
            action="escalate",
            attempts=attempts,
            exit_reason=(
                f"verify failed {attempts}x (cap {fix_cap}); last exit "
                f"{outcome.exit_code}. Tail:\n{outcome.tail}"
            ),
        )
    return GateDecision(
        action="retry",
        attempts=attempts,
        next_message=(
            "Verification failed. You reported the task complete, but the verify "
            f"command did not pass (exit {outcome.exit_code}). Fix the failures "
            "below and continue. Do not report complete again until they pass.\n\n"
            f"verify command:\n  {outcome.command}\n\n"
            f"output tail:\n{outcome.tail}"
        ),
    )
