from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import create_sdk_mcp_server, tool

from orchestrator.state import Decision, load_state, save_state


def build_update_state_handler(
    state_path: Path,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        kind = args.get("kind")
        try:
            state = load_state(state_path)
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
                state.files_touched.append(args["path"])
            elif kind == "commit":
                state.commits.append(args["sha"])
            elif kind == "step_completed":
                step_id = args["step_id"]
                for s in state.plan:
                    if s.id == step_id:
                        s.status = "completed"
                        break
            elif kind == "open_thread":
                state.open_threads.append(args["thread"])
            else:
                return {
                    "content": [
                        {"type": "text", "text": f"error: unknown kind '{kind}'"}
                    ]
                }
            save_state(state_path, state)
            return {"content": [{"type": "text", "text": f"ok: applied {kind}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"error: {e}"}]}

    return handler


def build_state_mcp_server(state_path: Path):
    handler = build_update_state_handler(state_path)

    @tool(
        "update_state",
        "Update the orchestrator's state.json. Use after each meaningful step.",
        {
            "kind": str,
            "turn": int,
            "question": str,
            "answer": str,
            "reasoning": str,
            "decided_by": str,
            "path": str,
            "sha": str,
            "step_id": int,
            "thread": str,
        },
    )
    async def update_state_tool(args: dict[str, Any]) -> dict[str, Any]:
        return await handler(args)

    return create_sdk_mcp_server(name="orchestrator-state", tools=[update_state_tool])
