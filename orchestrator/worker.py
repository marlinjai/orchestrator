import os
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from orchestrator.tools import build_state_mcp_server


WORKER_SYSTEM_PROMPT = """\
You are an autonomous Claude Code worker. You execute one task end to end with
no human in the loop. After each meaningful step, call the `update_state` tool
to record what you did (decisions, file edits, commits). Be terse in prose;
let your work speak through the state file and the git log.

Hard rules you must follow:
- Never run destructive shell commands (the orchestrator's denylist will block them anyway).
- Never send messages, comments, or PRs to external systems.
- Never spend money, deploy to prod, or modify infrastructure.
- If you genuinely cannot proceed without a human decision, write your question
  as your final message and stop. The Decision Proxy will handle it.
"""


def build_worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CLAUDE_DISABLE_HOOKS"] = "1"
    return env


def build_worker_options(
    *,
    state_path: Path,
    project_dir: Path,
    denied_bash: list[str],
) -> ClaudeAgentOptions:
    state_server = build_state_mcp_server(state_path)
    return ClaudeAgentOptions(
        system_prompt=WORKER_SYSTEM_PROMPT,
        cwd=str(project_dir),
        mcp_servers={"orchestrator-state": state_server},
        allowed_tools=[
            "Read",
            "Edit",
            "Write",
            "Bash",
            "Grep",
            "Glob",
            "WebSearch",
            "WebFetch",
            "mcp__orchestrator-state__update_state",
        ],
    )


async def run_worker_turn(
    *,
    client: ClaudeSDKClient,
    user_message: str,
) -> AsyncIterator[dict]:
    """Send user_message and yield streamed response events. Caller assembles output."""
    await client.query(user_message)
    async for msg in client.receive_response():
        yield msg
