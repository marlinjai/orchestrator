from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import create_sdk_mcp_server, tool
from pydantic import ValidationError

from orchestrator.state import CommitEntry, Decision, FileTouched, load_state, save_state


_SHA_CHARS = set("0123456789abcdef")


def _same_commit(a: str, b: str) -> bool:
    """Two SHAs name the same commit when one is a prefix of the other (a Worker
    may report the short form of a SHA reconcile recorded in full)."""
    a, b = a.lower(), b.lower()
    return len(a) >= 7 and len(b) >= 7 and (a.startswith(b) or b.startswith(a))


def _record_commit(state, sha: str, message: str) -> str:
    """Record a Worker-reported commit and return the tool's reply text.

    A report that matches a commit reconcile already found in git upgrades that
    entry to self-reported instead of appending a duplicate. Before this, a
    Worker that reported a commit after the end-of-turn reconcile (Mercury,
    in the 2026-09-28 race) left the "not self-reported" flag set forever, and
    the Decision Proxy kept sending it back until the stagnation guard stopped
    a run whose work was already done.
    """
    sha = sha.strip()
    if len(sha) < 7 or not set(sha.lower()) <= _SHA_CHARS:
        raise ValueError(
            f"sha {sha!r} is not a commit SHA: report a commit only AFTER `git commit`, "
            "passing the full SHA printed by `git rev-parse HEAD`"
        )
    matches = [e for e in state.commits if _same_commit(e.sha, sha)]
    on_baseline = bool(state.baseline_ref) and _same_commit(sha, state.baseline_ref)
    candidates = [e.sha for e in matches] + ([state.baseline_ref] if on_baseline else [])
    if any(not _same_commit(candidates[0], other) for other in candidates[1:]):
        raise ValueError(
            f"sha {sha!r} is ambiguous: it matches more than one known commit; "
            "report the full SHA printed by `git rev-parse HEAD`"
        )
    if on_baseline:
        raise ValueError(
            "that SHA is the run's starting commit, not your work: report the commit "
            "you created (`git rev-parse HEAD` right after your `git commit`)"
        )
    if matches:
        entry = matches[0]
        if entry.decided_by == "system":
            entry.decided_by = "proxy"
            if len(sha) > len(entry.sha):
                entry.sha = sha
            if message and not entry.message:
                entry.message = message
            return f"ok: commit {sha[:12]} was already in git; now marked as self-reported"
        return f"ok: commit {sha[:12]} was already recorded"
    state.commits.append(CommitEntry(sha=sha, message=message, decided_by="proxy"))
    return "ok: applied commit"


def _record_file(state, path: str) -> str:
    """Record a Worker-reported file; same upgrade-not-duplicate rule as commits."""
    for entry in state.files_touched:
        if entry.path == path:
            if entry.decided_by == "system":
                entry.decided_by = "proxy"
                return f"ok: {path} was already in git; now marked as self-reported"
            return f"ok: {path} was already recorded"
    state.files_touched.append(FileTouched(path=path, decided_by="proxy"))
    return "ok: applied file_touched"


def build_update_state_handler(
    state_path: Path,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build an async handler that mutates state.json. Not concurrency-safe; assumes sequential calls."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        kind = args.get("kind")
        try:
            state = load_state(state_path)
            reply = f"ok: applied {kind}"
            if kind == "decision":
                state.decisions.append(
                    Decision(
                        turn=args["turn"],
                        question=args["question"],
                        answer=args["answer"],
                        reasoning=args["reasoning"],
                        decided_by=args.get("decided_by", "proxy"),
                    )
                )
            elif kind == "file_touched":
                reply = _record_file(state, args["path"])
            elif kind == "commit":
                reply = _record_commit(state, args["sha"], args.get("message", ""))
            elif kind == "step_completed":
                step_id = args["step_id"]
                for s in state.plan:
                    if s.id == step_id:
                        s.status = "completed"
                        break
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"warning: no step with id={step_id}",
                            }
                        ]
                    }
            elif kind == "open_thread":
                state.open_threads.append(args["thread"])
            elif kind == "assumption":
                state.assumptions_made.append(args["assumption"])
            elif kind == "plan_contradiction":
                state.plan_contradictions.append(args["contradiction"])
            elif kind == "confidence":
                # Logged only, never a gate input (see State.confidence).
                state.confidence = float(args["confidence"])
            else:
                return {
                    "content": [
                        {"type": "text", "text": f"error: unknown kind '{kind}'"}
                    ]
                }
            save_state(state_path, state)
            return {"content": [{"type": "text", "text": reply}]}
        except (KeyError, ValueError, ValidationError, OSError) as e:
            return {"content": [{"type": "text", "text": f"error: {e}"}]}

    return handler


# The update_state tool contract, shared by every worker adapter: the Claude SDK
# MCP tool below and the OpenAI-compatible adapter's native function tool, so a
# Worker reports progress identically whatever model runs it. Explicit JSON
# schema with `required`, because dict-shorthand @tool makes every field required.
UPDATE_STATE_DESCRIPTION = (
    "Update the orchestrator's state.json. Use after each meaningful step. "
    "Pass `kind` plus only the fields relevant to that kind."
)
UPDATE_STATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "decision",
                "file_touched",
                "commit",
                "step_completed",
                "open_thread",
                "assumption",
                "plan_contradiction",
                "confidence",
            ],
        },
        "turn": {"type": "integer"},
        "question": {"type": "string"},
        "answer": {"type": "string"},
        "reasoning": {"type": "string"},
        "decided_by": {"type": "string"},
        "path": {"type": "string"},
        "sha": {"type": "string"},
        "message": {"type": "string"},
        "step_id": {"type": "integer"},
        "thread": {"type": "string"},
        "assumption": {"type": "string"},
        "contradiction": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["kind"],
}


def build_state_mcp_server(state_path: Path):
    handler = build_update_state_handler(state_path)

    @tool("update_state", UPDATE_STATE_DESCRIPTION, UPDATE_STATE_SCHEMA)
    async def update_state_tool(args: dict[str, Any]) -> dict[str, Any]:
        return await handler(args)

    return create_sdk_mcp_server(name="orchestrator-state", tools=[update_state_tool])
