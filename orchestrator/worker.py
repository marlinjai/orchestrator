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
from typing import AsyncIterator, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from orchestrator.tools import build_state_mcp_server

logger = logging.getLogger(__name__)


# Anthropic auth mode for the spawned SDK subprocess. "subscription" scrubs
# ANTHROPIC_API_KEY so the SDK uses the Claude login; "api_key" keeps it so the
# SDK bills the metered API. From 2026-06-15 headless/SDK use no longer draws
# from the flat subscription (it consumes a separate metered credit, then API
# rates), so this choice -- and the cost guard it pairs with -- is load-bearing
# for billing, not cosmetic.
AuthMode = Literal["subscription", "api_key"]


# Foreign LLM provider credentials and Anthropic auth-token overrides that are
# ALWAYS removed from the SDK subprocess env, in either auth mode, so a wrapper
# (Infisical, direnv, a parent shell export) cannot silently redirect auth or
# contaminate provider/model selection. ANTHROPIC_API_KEY is handled separately
# by auth_mode in apply_env_contract: it is the intentional subscription-vs-API
# switch, not cross-provider contamination.
CROSS_PROVIDER_KEY_DENYLIST: tuple[str, ...] = (
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
)


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


def apply_env_contract(auth_mode: AuthMode = "subscription") -> list[str]:
    """Normalize the SDK subprocess env to an explicit, auditable contract.

    Two concerns, one place:

    1. Cross-provider hygiene (always): foreign LLM provider keys and
       ANTHROPIC_AUTH_TOKEN (CROSS_PROVIDER_KEY_DENYLIST) are removed so a
       wrapper (Infisical, direnv, a parent shell export) cannot silently
       redirect auth or contaminate model selection.
    2. Anthropic auth mode (the load-bearing billing choice):
       - "subscription" (default): ANTHROPIC_API_KEY is removed so the SDK falls
         back to the Claude subscription login. This is the historical behavior.
         NOTE: from 2026-06-15, headless/SDK use no longer draws from the flat
         subscription; it consumes a separate metered credit, then API rates.
       - "api_key": ANTHROPIC_API_KEY is KEPT so the SDK bills the metered API.
         If the key is absent in this mode the run will fail auth, so we warn
         loudly. Pair this mode with a cost cap (guardrails.cost_cap_hit).

    Returns the env var NAMES actually removed, for run.log audit. Never logs or
    returns values.
    """
    removed: list[str] = []
    for var in CROSS_PROVIDER_KEY_DENYLIST:
        if os.environ.pop(var, None) is not None:
            removed.append(var)

    if auth_mode == "subscription":
        if os.environ.pop("ANTHROPIC_API_KEY", None) is not None:
            removed.append("ANTHROPIC_API_KEY")
    else:  # api_key: keep the key so the SDK bills the metered API
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning(
                "auth_mode=api_key but ANTHROPIC_API_KEY is not set; the SDK has "
                "no API credential and the run will likely fail auth"
            )

    if removed:
        logger.info(
            "env contract (auth_mode=%s) scrubbed: %s", auth_mode, ", ".join(removed)
        )
    else:
        logger.info("env contract (auth_mode=%s): nothing to scrub", auth_mode)
    return removed


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


def resolve_effective_mcp_servers(
    requested: list[str], ceiling: list[str] | None
) -> tuple[list[str], list[str]]:
    """Apply the operator's per-repo MCP-server ceiling to a goal's requested keys.

    The registry's ``allowed_mcp_servers`` (keyed by the project's real git
    remote, which a goal file cannot fake) is an operator CEILING: a goal can
    only enable a server the operator allowed for that repo. Returns
    ``(allowed, dropped)`` where ``dropped`` are the requested keys the ceiling
    forbids.

    Two invariants:
    - Safe defaults are never subject to the ceiling. Naming one is always
      allowed (it is added unconditionally elsewhere and can never be removed),
      so a default key never appears in ``dropped``.
    - A ``None`` ceiling means "no per-repo ceiling": every requested key passes
      through (the pre-brick-3 behavior), so repos with no registry entry are
      unaffected.
    """
    if ceiling is None:
        return list(requested), []
    ceiling_set = set(ceiling)
    allowed: list[str] = []
    dropped: list[str] = []
    for key in requested:
        if key in DEFAULT_MCP_SERVER_KEYS or key in ceiling_set:
            allowed.append(key)
        else:
            dropped.append(key)
    return allowed, dropped


def build_worker_options(
    *,
    state_path: Path,
    project_dir: Path,
    denied_bash: list[str],
    extras: WorkerExtras | None = None,
    auth_mode: AuthMode = "subscription",
    allowed_mcp_servers: list[str] | None = None,
) -> ClaudeAgentOptions:
    apply_env_contract(auth_mode)
    state_server = build_state_mcp_server(state_path)

    # Safe defaults, always present. A goal can union onto these but never drop
    # them.
    mcp_servers: dict[str, dict] = {
        "orchestrator-state": state_server,
        # Secrets proxy: credential-requiring commands route through this MCP
        # server (which calls the Tailscale-only proxy) instead of running
        # `infisical run` in Worker context, where raw secrets would land in
        # the subprocess env and the transcript sent to Anthropic.
        #
        # NEVER put the proxy token in this dict. The SDK serializes
        # `mcp_servers` into a `--mcp-config '{...}'` COMMAND LINE ARGUMENT, and
        # argv is world-readable: `ps aux` printed the token to anyone on the
        # machine. That is exactly how it leaked on 2026-08-17 and forced a
        # rotation. The MCP server now reads the token itself from a 0600 file
        # (~/.config/secrets-proxy/token, override with SECRETS_PROXY_TOKEN_FILE),
        # which cannot appear in argv and does not propagate to child processes.
        # With no readable token file the stdio server exits(1) at startup and
        # the tool simply degrades to unavailable.
        "secrets-proxy": {
            "type": "stdio",
            "command": "node",
            "args": ["/Users/marlinjai/software-dev/secrets-proxy/mcp/dist/index.js"],
            "env": {
                "SECRETS_PROXY_URL": "http://100.124.97.31:8765",
            },
        },
    }
    allowed_tools: list[str] = list(DEFAULT_ALLOWED_TOOLS)

    if extras is not None:
        # Operator ceiling FIRST: a goal can only enable servers the repo policy
        # allows (un-fakeable, keyed by the real git remote). Out-of-ceiling keys
        # are dropped before they ever reach the registry resolver. This governs
        # SERVERS; a goal-declared `mcp__<server>__*` tool for a server the
        # ceiling dropped is inert (the server is never configured) and harmless.
        allowed_keys, dropped_by_ceiling = resolve_effective_mcp_servers(
            extras.mcp_server_keys, allowed_mcp_servers
        )
        for key in dropped_by_ceiling:
            logger.warning(
                "goal requested MCP server %r not permitted by the repo policy "
                "ceiling %s; dropping",
                key,
                sorted(allowed_mcp_servers or []),
            )
        extra_servers, extra_server_tools = _resolve_extra_servers(allowed_keys)
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

    # Effective server set, for the audit trail (the orchestrator also prints
    # this to run.log; logging here covers direct/library callers).
    logger.info("worker mcp servers (effective): %s", sorted(mcp_servers))

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
