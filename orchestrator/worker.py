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
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from orchestrator.tools import build_state_mcp_server

logger = logging.getLogger(__name__)


# Servers and tools that are ALWAYS present in a Worker and can never be removed
# by a goal file. A goal may union additional servers/tools on top of these, but
# never drop them: dropping orchestrator-state would blind the control loop, and
# dropping secrets-proxy would push credential-requiring commands back into raw
# Worker context.
DEFAULT_MCP_SERVER_KEYS: frozenset[str] = frozenset({"orchestrator-state", "secrets-proxy"})
DEFAULT_ALLOWED_TOOLS: tuple[str, ...] = (
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
)


# Allowlist of MCP servers a goal file may opt its Worker into by name. This is
# the ONLY way a goal can add a server: a goal names a key from this registry,
# never an arbitrary stdio/env config. That contract is load-bearing for
# security: a goal file is data the orchestrator runs with the operator's
# credentials, so letting it inject arbitrary server configs (with arbitrary
# env, including secrets, or arbitrary commands) would be a trivial exfiltration
# / RCE channel. Every entry here is a vetted, NON-secret-leaking server.
#
# DO NOT add the Coolify MCP here: several of its tools (database create/get,
# env-var reveal) return connection strings and tokens in plaintext, which would
# land in the transcript sent to Anthropic. A Worker that needs Coolify uses the
# Coolify-via-proxy curl pattern instead (it already has the secrets-proxy MCP),
# where the proxy injects the API token server-side and redacts the response.
#
# Each entry is (server_config, tool_prefixes) where server_config is the SDK
# mcp_servers value and tool_prefixes are the `mcp__<server>__*` tool names that
# get unioned into allowed_tools when the server is enabled.
@dataclass(frozen=True)
class RegisteredServer:
    config: dict
    tools: tuple[str, ...] = ()


WORKER_MCP_REGISTRY: dict[str, RegisteredServer] = {
    "context7": RegisteredServer(
        config={
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
            "env": {},
        },
        tools=(
            "mcp__context7__resolve-library-id",
            "mcp__context7__query-docs",
        ),
    ),
}


@dataclass
class WorkerExtras:
    """Per-goal additions to the Worker's MCP servers and allowed tools.

    Both fields are pure additions (union onto the safe defaults). A goal can
    never remove a default server or tool: unknown server names are dropped with
    a logged warning rather than failing the run, so a typo in a goal file
    degrades to "the default Worker" instead of halting the orchestrator.
    """

    mcp_server_keys: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)


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


def load_worker_extras(frontmatter: dict) -> WorkerExtras:
    """Read the per-goal Worker MCP/tool additions from goal-file frontmatter.

    Recognized keys (both optional inline lists, matching the `verify` field's
    frontmatter style):

      worker_mcp_servers  list of server keys from WORKER_MCP_REGISTRY to enable
                          for this Worker (e.g. `[context7]`). A goal can ONLY
                          name a registered server; it cannot inject an arbitrary
                          stdio/env config. Unknown names are dropped with a
                          warning.
      worker_allowed_tools  list of extra tool names to union into allowed_tools
                          (e.g. extra built-in tools or `mcp__<server>__*`).

    Both fields are pure additions on top of the safe defaults. Neither can
    remove a default. Non-list values are ignored (degrade to no extras) rather
    than raising, so a malformed goal still runs the default Worker.
    """

    def _as_str_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return WorkerExtras(
        mcp_server_keys=_as_str_list(frontmatter.get("worker_mcp_servers")),
        allowed_tools=_as_str_list(frontmatter.get("worker_allowed_tools")),
    )


def _resolve_extra_servers(
    keys: list[str],
) -> tuple[dict[str, dict], list[str]]:
    """Resolve goal-declared server keys against the registry.

    Returns (servers, tools). A key not in WORKER_MCP_REGISTRY is skipped with a
    logged warning (the run continues with the default Worker rather than
    halting). A key naming a default server is a no-op: the defaults are added
    unconditionally elsewhere and can never be overridden by a goal.
    """
    servers: dict[str, dict] = {}
    tools: list[str] = []
    for key in keys:
        if key in DEFAULT_MCP_SERVER_KEYS:
            # Default servers are always present; naming one is harmless and a
            # goal cannot replace its config via this path.
            continue
        registered = WORKER_MCP_REGISTRY.get(key)
        if registered is None:
            logger.warning(
                "goal frontmatter requested unknown MCP server %r; "
                "ignoring (not in WORKER_MCP_REGISTRY: %s)",
                key,
                sorted(WORKER_MCP_REGISTRY),
            )
            continue
        servers[key] = dict(registered.config)
        tools.extend(registered.tools)
    return servers, tools


def build_worker_options(
    *,
    state_path: Path,
    project_dir: Path,
    denied_bash: list[str],
    extras: WorkerExtras | None = None,
) -> ClaudeAgentOptions:
    _scrub_anthropic_api_key()
    state_server = build_state_mcp_server(state_path)

    # Safe defaults, always present. A goal can union onto these but never drop
    # them.
    mcp_servers: dict[str, dict] = {
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
    }
    allowed_tools: list[str] = list(DEFAULT_ALLOWED_TOOLS)

    if extras is not None:
        extra_servers, extra_server_tools = _resolve_extra_servers(extras.mcp_server_keys)
        # Defaults win: never let a goal-resolved server clobber a default key.
        for key, cfg in extra_servers.items():
            mcp_servers.setdefault(key, cfg)
        # Union extra tools (registry-implied + goal-declared), preserving order
        # and dropping duplicates so the defaults always remain first.
        seen = set(allowed_tools)
        for tool in [*extra_server_tools, *extras.allowed_tools]:
            if tool not in seen:
                allowed_tools.append(tool)
                seen.add(tool)

    return ClaudeAgentOptions(
        system_prompt=WORKER_SYSTEM_PROMPT,
        cwd=str(project_dir),
        # Empty list = SDK isolation mode: skip user/project/local settings,
        # which is where hooks (and other dev-machine config) live. Without
        # this, the user's SessionStart/Stop/UserPromptSubmit hooks fire in
        # spawned Worker processes and pollute the agent context. This is ONLY
        # hook isolation; it does not gate MCP servers, which are passed
        # explicitly below.
        setting_sources=[],
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
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
