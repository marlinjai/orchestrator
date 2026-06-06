"""Worker agent options and turn loop.

Hook isolation: the orchestrator must run Worker (and Proxy) agents in a clean
context, free from the developer's personal hook configuration. Hooks are loaded
from filesystem settings (`~/.claude/settings.json`, `.claude/settings.json`,
`.claude/settings.local.json`), so the only reliable way to disable them from
the SDK is `setting_sources=[]` ("SDK isolation mode"). The legacy
`CLAUDE_DISABLE_HOOKS=1` env var is a no-op in the spawned CLI process and is
not used here.
"""

import logging
import os
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from orchestrator.tools import build_state_mcp_server

logger = logging.getLogger(__name__)


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

Edit discipline for shared index/status files (STATUS.md, ROADMAP.md, README
tables, registries, etc.):
- Touch ONLY the rows or entries that pertain to your specific task.
- Preserve the existing format exactly: same columns, same ordering, same
  separators, same wording conventions for status values. Match what is
  already in the file rather than inventing a "better" shape.
- Do NOT add columns, reformat tables, normalize whitespace, fix unrelated
  typos, or reorder rows. Format changes are out of scope for any task whose
  goal does not explicitly request them.
- If the existing file has no row for your task, add one row that mirrors the
  format of its neighbors. Do not change the schema to accommodate it.
- The spec file's frontmatter is the canonical source of truth for spec
  status. The index/status row is a reflection: mirror what you wrote in the
  spec frontmatter and match the format of adjacent rows.

When parallel tasks edit the same index file with different self-invented
formats, every run after the first becomes a merge conflict for the human
doing the integration. Stay in your lane.

Tool: execute_with_secrets
Use this instead of Bash for any command that requires Infisical secrets (database
migrations, API calls needing tokens, infisical run wrappers). Pass projectId and path
so the proxy fetches from the right Infisical location. Never run `infisical run`
directly via Bash -- it injects raw secrets into this process.
"""


def _scrub_anthropic_api_key() -> None:
    """Ensure the Claude Agent SDK subprocess uses subscription auth, not API billing.

    The CLI's auth precedence puts ANTHROPIC_API_KEY ahead of the ~/.config/claude
    login credentials. If the orchestrator is launched under `infisical run` (or any
    other wrapper that injects the key for downstream tools), the SDK silently
    switches to pay-per-token API billing on that key. The Worker doesn't need the
    key to author code that references it at runtime, so we drop it at the
    SDK-spawn boundary.
    """
    if os.environ.pop("ANTHROPIC_API_KEY", None) is not None:
        logger.info("scrubbed ANTHROPIC_API_KEY from env so SDK uses subscription auth")


def build_worker_options(
    *,
    state_path: Path,
    project_dir: Path,
    denied_bash: list[str],
) -> ClaudeAgentOptions:
    _scrub_anthropic_api_key()
    state_server = build_state_mcp_server(state_path)
    return ClaudeAgentOptions(
        system_prompt=WORKER_SYSTEM_PROMPT,
        cwd=str(project_dir),
        # Empty list = SDK isolation mode: skip user/project/local settings,
        # which is where hooks (and other dev-machine config) live. Without
        # this, the user's SessionStart/Stop/UserPromptSubmit hooks fire in
        # spawned Worker processes and pollute the agent context.
        setting_sources=[],
        mcp_servers={
            "orchestrator-state": state_server,
            # Secrets proxy: credential-requiring commands route through this MCP
            # server (which calls the Tailscale-only proxy) instead of running
            # `infisical run` in Worker context, where raw secrets would land in
            # the subprocess env and the transcript sent to Anthropic. If
            # SECRETS_PROXY_TOKEN is unset (e.g. bare `orchestrator start` not
            # launched via cc.sh), this stdio server exits(1) at startup and the
            # tool simply degrades to unavailable.
            "secrets-proxy": {
                "type": "stdio",
                "command": "node",
                "args": ["/Users/marlinjai/software-dev/secrets-proxy/mcp/dist/index.js"],
                "env": {
                    "SECRETS_PROXY_URL": "http://100.124.97.31:8765",
                    "PROXY_TOKEN": os.environ.get("SECRETS_PROXY_TOKEN", ""),
                },
            },
        },
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
            "mcp__secrets-proxy__execute_with_secrets",
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
