"""Roadmap consumption: turn the closed-loop-sync forward queue into a goal file.

This is the loop-closer (closed-loop-sync plan, Component 4b). It shells out to
the installed ``closed-loop-sync`` CLI (the two repos stay decoupled: the
orchestrator does NOT import the package) to get the ranked forward queue as
JSON, then scaffolds an orchestrator goal file from the top item.

Deliberately conservative: it picks the work item and scaffolds the goal, but
it does NOT guess the target repo / worktree (a roadmap plan can live in
knowledge-base while the implementation lands elsewhere; that mapping is human
judgment). The generated goal leaves ``--project`` for the operator to set
before dispatch. Everything here is pure/deterministic and unit-tested; the
only side effect (subprocess + file write) is isolated to thin wrappers.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


class RoadmapError(RuntimeError):
    pass


def fetch_ranked_items(roots, include_in_progress: bool = False,
                       cli: str = "closed-loop-sync") -> list[dict]:
    """Return the ranked forward queue via ``closed-loop-sync roadmap items``.

    Raises ``RoadmapError`` if the CLI is missing or returns non-JSON.
    """
    if not roots:
        raise RoadmapError("no roots given")
    cmd = [cli, "roadmap", "items"]
    for r in roots:
        cmd += ["--root", str(r)]
    if include_in_progress:
        cmd.append("--include-in-progress")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RoadmapError(f"{cli} not found on PATH; install closed-loop-sync") from exc
    except subprocess.CalledProcessError as exc:
        raise RoadmapError(f"{cli} failed: {exc.stderr.strip()}") from exc
    try:
        return json.loads(out.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RoadmapError(f"{cli} returned non-JSON output") from exc


def _slug(item: dict) -> str:
    """Stable kebab-case task-id from the plan filename stem, then title."""
    path = item.get("path")
    base = Path(path).stem if path else (item.get("title") or "roadmap-item")
    # Strip a leading YYYY-MM-DD- date prefix for a cleaner task id.
    base = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or "roadmap-item"


def item_to_goal(item: dict) -> tuple[str, str]:
    """Scaffold an orchestrator goal file from a ranked roadmap item.

    Returns ``(task_id, goal_markdown)``. The goal references the source plan
    as its spec and leaves the target ``--project`` for the operator (the
    repo mapping is not auto-guessed).
    """
    task_id = _slug(item)
    title = item.get("title", task_id)
    plan_path = item.get("path", "(unknown plan path)")
    status = item.get("status", "")
    leverage = item.get("leverage_label") or "UNSET"

    goal = f"""---
task: {task_id}
spec: {plan_path}
# TODO(operator): set --project to the target repo worktree before dispatch.
# A roadmap plan does not encode which repo implements it; assign deliberately.
verify: # TODO(operator): the target repo's gate, e.g. pnpm test && pnpm build && tsc --noEmit
---

# Goal

Implement the plan "{title}" (roadmap leverage: {leverage}, plan status: {status}).
Source plan (authoritative spec): `{plan_path}`.

## Read first

- The full source plan at `{plan_path}` (its Goal, Scope, Definition of done).
- The target repo's CLAUDE.md / README and any code the plan names as touchpoints.

## Definition of done

- Whatever the source plan's "Definition of done" lists.
- The target repo's verify command passes (fill the `verify:` frontmatter above).
- Update the source plan's frontmatter `status:` to reflect reality (in-progress while building, completed when done and verified).
- Single conventional-commit on this branch.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. Do not run destructive commands.
- When done, output a final completion message.
"""
    return task_id, goal


def write_goal(goal_md: str, task_id: str, goals_dir) -> Path:
    """Write the scaffolded goal to ``goals_dir/<task_id>.md`` and return the path."""
    goals_dir = Path(goals_dir)
    goals_dir.mkdir(parents=True, exist_ok=True)
    out = goals_dir / f"{task_id}.md"
    out.write_text(goal_md, encoding="utf-8")
    return out


def next_goal(roots, goals_dir, index: int = 0,
              include_in_progress: bool = False, cli: str = "closed-loop-sync") -> dict:
    """Pick the item at ``index`` of the ranked queue and scaffold its goal.

    Returns a summary dict ``{task_id, goal_path, item, total}``. Raises
    ``RoadmapError`` if the queue is empty or ``index`` is out of range.
    """
    items = fetch_ranked_items(roots, include_in_progress=include_in_progress, cli=cli)
    if not items:
        raise RoadmapError("roadmap forward queue is empty")
    if index < 0 or index >= len(items):
        raise RoadmapError(f"index {index} out of range (queue has {len(items)})")
    item = items[index]
    task_id, goal_md = item_to_goal(item)
    path = write_goal(goal_md, task_id, goals_dir)
    return {"task_id": task_id, "goal_path": str(path), "item": item, "total": len(items)}
