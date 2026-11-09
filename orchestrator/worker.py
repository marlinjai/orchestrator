"""Worker agent options and turn loop.

Hook isolation: the orchestrator must run Worker (and Proxy) agents in a clean
context, free from the developer's personal hook configuration. Hooks are loaded
from filesystem settings (`~/.claude/settings.json`, `.claude/settings.json`,
`.claude/settings.local.json`), so the only reliable way to disable them from
the SDK is `setting_sources=[]` ("SDK isolation mode"). The legacy
`CLAUDE_DISABLE_HOOKS=1` env var is a no-op in the spawned CLI process and is
not used here.
"""

import functools
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput, SandboxSettings

from orchestrator.guardrails import bash_allowed
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


# Credentials a Worker must never hold: they are removed from the orchestrator's
# own environment before the SDK spawns the Worker (the orchestrator itself uses
# none of them), so nothing in the Worker's shell can authenticate to a remote.
WORKER_CREDENTIAL_ENV_DENYLIST: tuple[str, ...] = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GITLAB_TOKEN",
    "GIT_ASKPASS",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
    "NPM_TOKEN",
    "NODE_AUTH_TOKEN",
    "HF_TOKEN",
    "INFISICAL_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


def worker_credential_env(private_dir: Path) -> dict[str, str]:
    """Environment overrides under which a Worker's git and gh hold no usable
    credentials, for the Claude Worker's CLI (so its Bash inherits them) and the
    Mercury adapter's `run_command`.

    gh and git's osxkeychain helper keep their token in the macOS Keychain, which
    scrubbing environment variables does not touch, so the Worker is pointed at
    EMPTY configuration instead: `GH_CONFIG_DIR` an empty directory, git's global
    config a file with only the user's name and email (commits need them) and no
    credential helper, `GIT_CONFIG_NOSYSTEM` (the Xcode system gitconfig sets
    `credential.helper osxkeychain`), a `credential.helper` reset through
    `GIT_CONFIG_COUNT`, no terminal prompt and a failing askpass.

    This does NOT close the Keychain: a process that talks to the keychain daemon
    itself (`security find-*`, git's osxkeychain helper run directly) is not
    stopped by any of it. The Mercury sandbox denies the daemon's mach lookup; the
    Claude CLI's sandbox has no such setting, so for the Claude Worker the only
    real boundary is a separate macOS user or a keychain-less host.
    """
    private_dir.mkdir(parents=True, exist_ok=True)
    gh_config = private_dir / "gh-config"
    gh_config.mkdir(exist_ok=True)
    gitconfig = private_dir / "gitconfig"
    lines = []
    for key in ("name", "email"):
        out = subprocess.run(["git", "config", "--global", "--get", f"user.{key}"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            lines.append(f"\t{key} = {out.stdout.strip()}")
    gitconfig.write_text("[user]\n" + "\n".join(lines) + "\n" if lines else "")
    return {
        "GH_CONFIG_DIR": str(gh_config),
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GCM_INTERACTIVE": "never",
        # Claude Code strips its own credentials from the environment of the
        # processes it starts for the Worker (Bash, hooks, MCP stdio servers).
        "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
    }


# Servers and tools that are ALWAYS present in a Worker and can never be removed
# by a goal file. A goal may union additional servers/tools on top of these, but
# never drop them: dropping orchestrator-state would blind the control loop, and
# dropping secrets-proxy would push credential-requiring commands back into raw
# Worker context.
DEFAULT_MCP_SERVER_KEYS: frozenset[str] = frozenset(
    {"orchestrator-state", "secrets-proxy"}
)
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
- You work inside a sandbox: you can write only in your worktree, its temp dirs and your own branch (commit, amend and rebase work). Creating or deleting branches, tags and stashes, `git fetch`/`gc`/`config`, writing outside the worktree, and any credentialed or remote action are refused by design.
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
    for var in (*CROSS_PROVIDER_KEY_DENYLIST, *WORKER_CREDENTIAL_ENV_DENYLIST):
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


# File-editing tools whose input carries the path the Worker is about to write
# to, and the input keys that hold it (NotebookEdit names it `notebook_path`).
# Checked by the PreToolUse hook built in `build_confinement_hook`.
PATH_GUARDED_TOOLS: frozenset[str] = frozenset(
    {"Write", "Edit", "NotebookEdit", "MultiEdit"}
)
PATH_INPUT_KEYS: tuple[str, ...] = ("file_path", "notebook_path")


def path_outside_root(raw: str | None, project_root: Path) -> Path | None:
    """The one worktree-confinement check, shared by every worker adapter.

    Resolve ``raw`` (absolute, or relative to ``project_root``) and return the
    resolved path when it escapes ``project_root``, else None. ``project_root``
    must already be resolved (realpath). Symlinks are followed, so a link
    pointing out of the worktree is caught too. A path that cannot be resolved is
    reported as outside (fail closed).
    """
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, ValueError, RuntimeError):
        # A path that cannot be resolved (a symlink loop, a NUL byte, an
        # unreadable component) cannot be shown to be inside: it is refused.
        # A confinement check fails closed; the tool would fail on it anyway.
        return candidate
    if resolved == project_root or project_root in resolved.parents:
        return None
    return resolved


def build_confinement_hook(project_dir: Path):
    """Build the PreToolUse hook that confines the structured file-editing tools
    (Write, Edit, MultiEdit, NotebookEdit) to ``project_dir``.

    A hook, not `can_use_tool`: the SDK consults `can_use_tool` only for tools
    that are NOT already in `allowed_tools`, and the Worker's defaults allow
    Write and Edit outright, so a `can_use_tool` guard was never called (proved
    with the real SDK on 0.2.93 and 0.2.121: the callback ran zero times and the
    out-of-worktree file was written). PreToolUse hooks run before every tool
    call regardless of `allowed_tools`.

    Paths are resolved with symlinks followed and `..` collapsed
    (`path_outside_root`), so an absolute path, a `../` escape and a symlink
    inside the worktree that points outside are all denied. This closes the
    2026-08-01 bug where a Worker given a prepared worktree edited the repo's
    main checkout instead (`cwd` only sets the starting directory).

    It covers only the structured tools. A Bash command can write anywhere the
    OS lets the process write; that is confined by the sandbox in
    `build_bash_sandbox`, not by anything this hook could parse out of a shell
    string.
    """
    project_root = project_dir.resolve()

    def bash_refusal(command: str) -> str | None:
        allowed, why = bash_allowed(command)
        return None if allowed else f"Refused by the orchestrator's command denylist: {why}."

    def refusal(tool_name: str, tool_input: dict) -> str | None:
        """Why this call is refused, or None when it stays inside the worktree.
        May raise on a path it cannot resolve; the caller treats that as a refusal."""
        for key in PATH_INPUT_KEYS:
            raw = tool_input.get(key)
            if not raw:
                continue
            raw = str(raw)
            # Only an absolute path can be judged here. A relative path is
            # resolved by the tool against a base this hook cannot see (the
            # session's current directory moves with `cd`, and a symlink inside
            # can redirect it), and `~` is expanded by the tool, not by us: both
            # could land outside while looking inside, so they are refused and
            # the Worker is told to use an absolute path.
            if not os.path.isabs(raw) or raw.startswith("~"):
                return (
                    f"Refused: {tool_name} was given {raw!r}. Use an absolute path inside "
                    f"the assigned worktree {project_root}."
                )
            resolved = Path(raw).resolve()
            if resolved != project_root and project_root not in resolved.parents:
                return (
                    f"Refused: {tool_name} targeted {resolved}, which is outside the "
                    f"assigned project root {project_root}. Only edit files inside the "
                    "assigned worktree."
                )
            # Every component of the path the CLI will open must be what it
            # looks like: a symlink inside the worktree could be re-pointed
            # between this check and the CLI's write (a time-of-check to
            # time-of-use race), so a path that goes through one is refused and
            # the Worker is given the canonical path. Residual: a component
            # swapped for a symlink in the instant between this check and the
            # open, by another process or a parallel Bash call in the same turn,
            # is not caught; the OS sandbox still confines what that write can
            # reach, and git records what changed.
            if str(resolved) != os.path.normpath(raw):
                return (
                    f"Refused: {tool_name} was given {raw!r}, a path through a symlink or `..`. "
                    f"Use the canonical path {resolved}."
                )
            # A file with several hard links is one inode under several names:
            # writing it here can change a file outside the worktree.
            if resolved.is_file() and resolved.stat().st_nlink > 1:
                return (
                    f"Refused: {tool_name} targeted {resolved}, which has other hard links "
                    "(it may be the same file as one outside the worktree)."
                )
        return None

    async def confine(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        tool_name = input_data.get("tool_name", "")
        if tool_name == "Bash":
            # Defence in depth: the denylist the Mercury adapter's run_command
            # also applies (`guardrails.bash_allowed`). A pattern list is not a
            # boundary (a shell can say the same thing many ways); what makes
            # remote writes impossible is that the Worker holds no credentials
            # (`worker_credential_env`) and cannot write outside its worktree.
            why = bash_refusal(str((input_data.get("tool_input") or {}).get("command", "")))
            if why is None:
                return {}
            logger.error("worker Bash denied: %s", why)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": why,
                }
            }
        if tool_name not in PATH_GUARDED_TOOLS:
            return {}
        try:
            reason = refusal(tool_name, input_data.get("tool_input") or {})
        except Exception as exc:  # noqa: BLE001 - a security hook fails closed
            # A NUL byte (ValueError), a symlink loop (RuntimeError), an
            # unreadable path (OSError): anything the check could not decide is
            # a refusal, never an allow (a failing hook is non-blocking in the CLI).
            reason = (
                f"Refused: {tool_name} could not be checked ({type(exc).__name__}); "
                "use a plain absolute path inside the assigned worktree "
                f"{project_root}."
            )
        if reason is None:
            return {}
        logger.error("worker tool %s denied: %s", tool_name, reason)
        # Deny AND stop the turn: an attempt to leave the worktree is not a
        # mistake to retry around (the old guard interrupted too, so the run
        # escalates instead of carrying on).
        return {
            "continue_": False,
            "stopReason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }

    return confine


SANDBOX_EXEC = "/usr/bin/sandbox-exec"


class ConfinementUnavailableError(RuntimeError):
    """The OS sandbox that confines a Worker's Bash cannot run here. Raised
    instead of starting an unconfined Worker."""


def require_sandbox_platform(*, need_socat: bool = True, probe_args: tuple[str, ...] = ()) -> None:
    """Raise ConfinementUnavailableError unless an OS sandbox can run here:
    Seatbelt (`sandbox-exec`) on macOS, bubblewrap with working user namespaces
    on Linux (and socat, which the Claude CLI's network proxy needs:
    ``need_socat``). Shared by the Claude Worker's Bash sandbox and the Mercury
    adapter's `run_command`, so neither can run unconfined by accident.
    ``probe_args`` are extra bwrap flags the real invocation uses, so the probe
    fails exactly where the real command would."""
    if sys.platform == "darwin":
        if not os.path.exists(SANDBOX_EXEC):
            raise ConfinementUnavailableError(f"the macOS sandbox ({SANDBOX_EXEC}) is missing")
    elif sys.platform.startswith("linux"):
        missing = [tool for tool in ("bwrap", "socat") if (need_socat or tool != "socat") and shutil.which(tool) is None]
        if missing:
            raise ConfinementUnavailableError(
                f"the Bash sandbox needs {' and '.join(missing)} on Linux; install "
                "bubblewrap and socat rather than run a Worker unconfined"
            )
        # Both installed is not enough: an AppArmor policy (Ubuntu 24.04) can
        # forbid the unprivileged user namespaces bubblewrap needs, and the
        # session would then fail at its first Bash call. Fail here instead.
        try:
            probe = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", *probe_args, "--unshare-user", "true"],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ConfinementUnavailableError(f"the Bash sandbox could not be started: {exc}") from exc
        if probe.returncode != 0:
            raise ConfinementUnavailableError(
                "bubblewrap cannot create a user namespace here "
                f"({probe.stderr.decode(errors='replace').strip() or 'no detail'}); "
                "enable unprivileged user namespaces rather than run a Worker unconfined"
            )
    else:
        raise ConfinementUnavailableError(
            f"the Bash sandbox is not available on {sys.platform}; refusing to "
            "run a Worker with unconfined Bash"
        )


@dataclass(frozen=True)
class GitLayout:
    """Where a work dir's git state lives. In a LINKED worktree (how every
    `--worktree` / batch Worker runs) `git_dir` is its own admin dir under the
    main checkout's `.git`, and `common_dir` is that main `.git`, SHARED with the
    main checkout and every other worktree: its refs, HEAD, index, packed-refs,
    info and objects are not the Worker's to write. In a plain repo both are the
    work dir's own `.git`."""

    work: Path
    git_dir: Path
    common_dir: Path
    branch: str | None  # the branch the work dir has checked out (None: detached)

    @property
    def linked(self) -> bool:
        return self.git_dir != self.common_dir

    @property
    def own_ref(self) -> Path | None:
        return self.common_dir / "refs" / "heads" / self.branch if self.branch else None


def _rev(work_dir: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(work_dir), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


@functools.lru_cache(maxsize=64)
def _git_dirs(work_dir: Path) -> tuple[Path, Path] | None:
    """The git dir and the common git dir of ``work_dir`` (None outside a repo).
    Cached: they never move during a run. Relative answers are resolved against
    ``work_dir`` (works on any git version)."""

    def resolved(raw: str) -> Path | None:
        if not raw:
            return None
        path = Path(raw)
        return (path if path.is_absolute() else work_dir / path).resolve()

    git_dir = resolved(_rev(work_dir, "rev-parse", "--git-dir"))
    common_dir = resolved(_rev(work_dir, "rev-parse", "--git-common-dir"))
    return (git_dir, common_dir) if git_dir is not None and common_dir is not None else None


def _git_layout(work_dir: Path) -> GitLayout | None:
    """The git layout of ``work_dir``, or None outside a repo. The branch is read
    fresh every time (a Worker may switch branches, a resume may find another one);
    the directories are cached."""
    dirs = _git_dirs(work_dir)
    if dirs is None:
        return None
    return GitLayout(work_dir, dirs[0], dirs[1], _rev(work_dir, "symbolic-ref", "-q", "--short", "HEAD") or None)


def _git_refs(layout: GitLayout) -> list[str]:
    """Every ref of the repository (loose and packed)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(layout.work), "for-each-ref", "--format=%(refname)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.split() if out.returncode == 0 else []


def git_deny_write_paths(layout: GitLayout) -> list[Path]:
    """What a Worker in a LINKED worktree must not write inside the shared git
    dir, as paths to deny (for the Claude CLI's sandbox, which takes deny lists,
    not allow-lists, and in which a deny always wins over an allow). Everything
    except the Worker's own branch ref, its reflog, its own admin dir and the
    object store: every other ref, HEAD, index, packed-refs, info, hooks, config,
    the other worktrees' admin dirs. `<work>/.git` (a file in a linked worktree)
    cannot be rewritten to point elsewhere or turned into a directory with its own
    config, which would run code the next time the orchestrator invokes git there."""
    common, own = layout.common_dir, layout.own_ref
    deny = [layout.work / ".git"]
    deny += [common / n for n in os.listdir(common) if n not in ("objects", "worktrees", "logs", "refs")]
    deny += [common / n for n in ("packed-refs", "info", "hooks", "config", "HEAD", "index")]
    for ref in _git_refs(layout):
        if common / ref != own:
            deny += [common / ref, common / "logs" / ref]
    refs_dir = common / "refs"
    if refs_dir.is_dir():
        deny += [refs_dir / n for n in os.listdir(refs_dir) if n != "heads"]
    deny += [refs_dir / n for n in ("tags", "remotes", "replace", "notes", "stash")]
    deny.append(common / "logs" / "HEAD")
    wt = common / "worktrees"
    if wt.is_dir():
        deny += [d for d in wt.iterdir() if d != layout.git_dir]
    deny += [layout.git_dir / n for n in ("commondir", "gitdir", "config.worktree")]
    return list(dict.fromkeys(deny))


# Credential files and directories a Worker never needs and must not read: ssh
# keys, gh's and git's stored logins, cloud and registry tokens. The Keychain is
# NOT covered by file rules (its daemon reads the files, not the Worker): on
# macOS the Mercury sandbox denies the keychain daemon's mach lookup; the Claude
# CLI's own sandbox offers no such rule (see worker_credential_env).
CREDENTIAL_READ_DENY: tuple[str, ...] = (
    "~/.ssh",
    "~/.gnupg",
    "~/.config/gh",
    "~/.config/git",
    "~/.gitconfig",
    "~/.git-credentials",
    "~/.netrc",
    "~/.aws",
    "~/.kube",
    "~/.docker",
    "~/.npmrc",
    "~/.config/infisical",
    "~/.infisical",
    "~/Library/Keychains",
)


def credential_read_denies() -> list[Path]:
    home = Path.home()
    return [home / p[2:] for p in CREDENTIAL_READ_DENY]


def _sbpl_string(path: Path | str) -> str:
    if any(c in str(path) for c in ('"', "\n")):
        raise ConfinementUnavailableError(f"a path with a quote or newline cannot be put in a sandbox profile: {path!r}")
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


# macOS: LaunchServices and launchd start processes OUTSIDE the sandbox on a
# caller's behalf (`open -a Terminal x.command`, `open -a <app>`), so a confined
# command could hand its work to an unconfined one; the keychain daemon would
# hand the Worker the user's stored logins (`security find-internet-password`,
# git's osxkeychain helper, gh). Their mach lookups are denied (proved: `open -g
# -j -a Calculator` starts the app under a profile without this and fails with
# it; the keychain items are readable without it and not with it; git, DNS and
# curl keep working).
_MACOS_DENIED_MACH_SERVICES = (
    "com.apple.coreservices.launchservicesd",
    "com.apple.lsd.mapdb",
    "com.apple.lsd.modifydb",
    "com.apple.lsd.open",
    "com.apple.coreservices.quarantine-resolver",
    "com.apple.SecurityServer",
    "com.apple.secd",
    "com.apple.securityd",
)

# The Linux argv's own flags, also used by the preflight probe so it fails where
# the real command would (an unprivileged container may allow user namespaces
# but refuse the /proc mount).
_BWRAP_FLAGS = ("--dev", "/dev", "--proc", "/proc", "--die-with-parent")

_EMPTY_DIR: Path | None = None


def _empty_dir() -> Path:
    """An empty directory (made once) to bind read-only over a path that does not
    exist yet, so a command cannot create it there."""
    global _EMPTY_DIR
    if _EMPTY_DIR is None or not _EMPTY_DIR.exists():
        _EMPTY_DIR = Path(tempfile.mkdtemp(prefix="orchestrator-empty-"))
    return _EMPTY_DIR


_SBPL_WRITE_OPS = "file-write* file-write-create file-write-data file-write-mode file-write-times file-write-flags file-write-unlink"


def _sbpl_write_rules(layout: GitLayout | None, root: Path, tmp: Path) -> str:
    """Seatbelt write rules: deny everything, then allow the work dir, temp dirs
    and the git paths the Worker needs; the last matching rule wins."""
    allow_paths = [root, tmp, Path("/private/tmp"), Path("/private/var/tmp")]
    denied: list[str] = []
    extra = ""
    if layout is not None and not layout.linked:
        # A plain repo: the git dir is inside the work dir. Keep it as an entry
        # (no `mv .git .g` and rebuild), and its hooks and config read-only.
        g = layout.git_dir
        denied += [f"(literal {_sbpl_string(g)})", f"(subpath {_sbpl_string(g / 'hooks')})", f"(literal {_sbpl_string(g / 'config')})"]
    elif layout is not None:
        # A LINKED worktree: ONLY its own admin dir, its own branch ref (and lock)
        # and reflog, and the object store (create-only: no overwriting or
        # deleting an existing object) are writable in the shared git dir.
        # The rest of it (other refs, HEAD, index, packed-refs, info, hooks,
        # config, other worktrees) stays denied by the blanket deny above.
        allow_paths.append(layout.git_dir)
        denied += [f"(literal {_sbpl_string(layout.work / '.git')})"]
        # `objects/info/alternates` would repoint the object store (a new file is
        # a create, which the create-only objects rule allows): keep the dir out.
        denied += [f"(subpath {_sbpl_string(layout.common_dir / 'objects' / 'info')})"]
        # `objects/pack` too: a forged pack shadows existing objects (git reads
        # packs before loose objects); a commit writes loose objects only, so
        # `git gc` / `repack` / `fetch` are refused here.
        denied += [f"(subpath {_sbpl_string(layout.common_dir / 'objects' / 'pack')})"]
        denied += [f"(literal {_sbpl_string(layout.git_dir / n)})" for n in ("commondir", "gitdir", "config.worktree")]
        own = layout.own_ref
        if own is not None:
            log = layout.common_dir / "logs" / "refs" / "heads" / (layout.branch or "")
            allow_paths += [own, own.with_name(own.name + ".lock"), log, log.with_name(log.name + ".lock")]
            extra += f"(allow file-write-create (subpath {_sbpl_string(log.parent)}))"
        objects = layout.common_dir / "objects"
        tmp_object = r"^" + re.escape(str(objects)) + r"/(.*/)?tmp_[^/]*$"
        extra += (
            f"(allow file-write-create (subpath {_sbpl_string(objects)}))"
            f'(allow file-write-data file-write-mode file-write-times file-write-flags file-write-unlink (regex #"{tmp_object}"))'
        )
    allow = " ".join(f"(subpath {_sbpl_string(p)})" for p in allow_paths)
    rules = (
        "(deny file-write*)"
        f"(allow file-write* {allow}"
        ' (literal "/dev/null") (literal "/dev/zero") (literal "/dev/tty") (subpath "/dev/fd")'
        ' (regex #"^/dev/ttys[0-9]+$"))'
        + extra
    )
    if denied:
        # The operations are named: Seatbelt lets an allow of a SPECIFIC operation
        # (the create-only object store rules above) win over a deny of the
        # `file-write*` wildcard, whatever the order (proved with the real
        # profile: a new `objects/info/alternates` was writable).
        rules += f"(deny {_SBPL_WRITE_OPS} {' '.join(denied)})"
    return rules


def sandboxed_command_argv(command: str, work_dir: Path) -> list[str]:
    """argv that runs ``command`` in bash under the same write confinement as the
    Claude Worker's Bash sandbox: filesystem writes only in ``work_dir``, the
    git paths a commit in it writes, and temp dirs (`/tmp`, `/var/tmp` and the
    user's temp dir). Used by the Mercury adapter's `run_command`, which has no
    SDK sandbox to switch on.

    In a linked worktree the shared `.git` is NOT writable except for the
    Worker's own branch ref, its reflog, its own admin dir and the object store
    (see `GitLayout`). On macOS (Seatbelt through `sandbox-exec`) the object
    store is create-only: an existing object cannot be overwritten or deleted. On
    Linux (bubblewrap, root read-only plus binds) the object store is writable as
    a whole and the Worker's refs namespace directory is writable (so refs of
    sibling branches in the same namespace are too); a branch with no namespace
    (`feature`, not `orchestrator/x`) cannot be confined there and is refused.
    Credential files are unreadable and, on macOS, the keychain daemon and
    LaunchServices are unreachable. Raises ConfinementUnavailableError when no
    sandbox can run here; the caller must then refuse the command, never run it
    unconfined. Network is not restricted (as for the Claude Worker).
    """
    require_sandbox_platform(need_socat=False, probe_args=_BWRAP_FLAGS)
    root = work_dir.resolve()
    layout = _git_layout(root)
    if layout is not None and layout.linked and layout.own_ref is not None:
        # The ref and reflog directories of the Worker's own branch must exist
        # (a branch that lives only in packed-refs has none): created here, on
        # the host, so the sandbox never needs a create right on them.
        layout.own_ref.parent.mkdir(parents=True, exist_ok=True)
        (layout.common_dir / "logs" / "refs" / "heads" / (layout.branch or "")).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir()).resolve()
    if sys.platform == "darwin":
        mach = " ".join(f'(global-name "{name}")' for name in _MACOS_DENIED_MACH_SERVICES)
        reads = " ".join(f"(subpath {_sbpl_string(p)})" for p in credential_read_denies())
        # the launchd-managed ssh-agent socket (SSH_AUTH_SOCK is scrubbed, the socket is not gone)
        agent = '(deny network-outbound (remote unix-socket (regex #"^/private/tmp/com\\.apple\\.launchd\\.[^/]+/Listeners$")))'

        profile = (
            "(version 1)(allow default)"
            + _sbpl_write_rules(layout, root, tmp)
            + f"(deny mach-lookup {mach})"
            + f"(deny file-read* {reads})"
            + agent
        )
        return [SANDBOX_EXEC, "-p", profile, "/bin/bash", "-c", command]
    argv = ["bwrap", "--ro-bind", "/", "/", *_BWRAP_FLAGS]
    binds = [root, tmp, *(p for p in (Path("/tmp"), Path("/var/tmp")) if p.exists())]
    protected: list[Path] = []
    if layout is not None and not layout.linked:
        protected += [layout.git_dir / "hooks", layout.git_dir / "config"]
    elif layout is not None:
        binds += [layout.git_dir, layout.common_dir / "objects"]
        protected += [layout.work / ".git", *(layout.git_dir / n for n in ("commondir", "gitdir", "config.worktree"))]
        protected += [layout.common_dir / "objects" / "info", layout.common_dir / "objects" / "pack"]
        own = layout.own_ref
        if own is not None:
            if own.parent == layout.common_dir / "refs" / "heads":
                raise ConfinementUnavailableError(
                    f"branch {layout.branch!r} has no namespace (`orchestrator/<task>`), so on Linux its ref "
                    "cannot be made writable without making every branch of the shared .git writable; "
                    "use a namespaced branch for the worktree"
                )
            logs = layout.common_dir / "logs" / "refs" / "heads" / (layout.branch or "")
            binds += [own.parent, logs.parent]
    for path in dict.fromkeys(p.resolve() for p in binds):
        argv += ["--bind", str(path), str(path)]
    for path in protected:
        if path.is_dir() or not path.exists():
            argv += ["--ro-bind", str(path if path.exists() else _empty_dir()), str(path)]
        else:
            argv += ["--ro-bind", str(path), str(path)]
    for path in credential_read_denies():
        if path.exists():
            argv += ["--ro-bind", str(_empty_dir()), str(path)] if path.is_dir() else ["--ro-bind", "/dev/null", str(path)]
    return [*argv, "--chdir", str(root), "/bin/bash", "-c", command]


def _claude_sandbox_filesystem(project_dir: Path) -> dict:
    """The Claude CLI sandbox's filesystem rules (deny lists: a deny wins over an
    allow, so the shared git dir is denied path by path rather than allowed path
    by path): the shared `.git` of a linked worktree except the Worker's own
    branch and admin dir and the object store, the `.git` entry of a plain repo,
    existing pack files and the object store's `info` (alternates would repoint
    the object store), and the credential files."""
    layout = _git_layout(project_dir.resolve())
    deny: list[Path] = []
    if layout is not None and layout.linked:
        deny += git_deny_write_paths(layout)
        objects = layout.common_dir / "objects"
        # `info` (alternates would repoint the object store) and `pack` (a forged
        # pack shadows existing objects: git reads packs before loose objects);
        # a commit writes loose objects only.
        deny += [objects / "info", objects / "pack"]
    elif layout is not None:
        deny.append(layout.git_dir)
    return {
        "denyWrite": [str(p) for p in dict.fromkeys(deny)],
        "denyRead": [str(p) for p in credential_read_denies()],
    }


def build_bash_sandbox(project_dir: Path | None = None) -> SandboxSettings:
    """The Claude Code sandbox settings that confine a Worker's Bash.

    With the sandbox on, the CLI runs every Bash command under the OS sandbox
    (Seatbelt on macOS, bubblewrap on Linux) whose filesystem writes are limited
    to the session's cwd (the task worktree), its git metadata and temp dirs; a
    write anywhere else fails with "Operation not permitted". Proved with the
    real SDK: `echo > /outside`, `cp`, `mv`, `tee` and `python -c` all fail,
    while the same commands inside the worktree, and `git commit` in a linked
    worktree, work (`scripts/prove_confinement.py`).

    `allowUnsandboxedCommands` is False so a Worker cannot ask for a command to
    run outside the sandbox (`dangerouslyDisableSandbox`), and `failIfUnavailable`
    makes a sandbox that cannot start an error, never a silent unconfined Bash.

    Network: the sandbox also proxies Bash's network and, by default, allows no
    domain at all (curl, git fetch, package installs fail). This confinement is
    about filesystem writes, and Worker egress was unrestricted before it, so
    every domain stays allowed; narrowing egress is a separate decision.

    Known consequence: a command that writes a global cache outside the
    worktree (`npm`'s ~/.npm, a pnpm store under ~/Library, ~/.cache) fails
    inside the sandbox, which is the point; such a command must keep its cache
    inside the worktree or the temp dir.
    """
    require_sandbox_platform()
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,
        **({"filesystem": _claude_sandbox_filesystem(project_dir)} if project_dir is not None else {}),  # type: ignore[typeddict-unknown-key]
        # If the sandbox cannot start (no bubblewrap namespaces, a missing
        # dependency), fail the session instead of running Bash unconfined.
        # The key is read by the CLI but is not in the SDK's TypedDict yet.
        "failIfUnavailable": True,  # type: ignore[typeddict-unknown-key]
        "network": {"allowedDomains": ["*"]},
    }


# Built-in tools a goal may pre-approve for its Worker. Anything else, in
# particular a permission RULE such as `Bash(git push:*)` or `Edit(//**)`, or an
# MCP tool of a server that is not configured, is not what a goal file may add.
KNOWN_BUILTIN_TOOLS: frozenset[str] = frozenset(
    {"Read", "Edit", "MultiEdit", "Write", "NotebookEdit", "Bash", "Grep", "Glob", "WebSearch", "WebFetch", "TodoWrite"}
)
_MCP_TOOL = re.compile(r"mcp__(?P<server>[A-Za-z0-9_-]+)__(?:\*|[A-Za-z0-9_.-]+)")


def _vetted_extra_tool(tool: str, mcp_servers: dict) -> bool:
    if tool in KNOWN_BUILTIN_TOOLS:
        return True
    match = _MCP_TOOL.fullmatch(tool)
    return match is not None and match.group("server") in mcp_servers


def build_worker_options(
    *,
    state_path: Path,
    project_dir: Path,
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
        # NEVER put a token in this dict. There is no shared proxy token to put
        # here any more: the MCP client mints its own short-lived access token
        # from the operator's own Infisical machine identity, read out of the
        # macOS Keychain (infisical-mi-<org>). Even so, the SDK serializes
        # `mcp_servers` into a `--mcp-config '{...}'` COMMAND LINE ARGUMENT, and
        # argv is world-readable: `ps aux` printed a token to anyone on the
        # machine back when one lived in this env dict. That is exactly how it
        # leaked on 2026-08-17 and forced a rotation, so this config carries
        # only the non-secret proxy URL, nothing that could regress that leak.
        # With no Keychain identity provisioned the stdio server exits(1) at
        # startup and the tool simply degrades to unavailable.
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
        vetted = [t for t in extras.allowed_tools if _vetted_extra_tool(t, mcp_servers)]
        for tool in set(extras.allowed_tools) - set(vetted):
            logger.warning("goal requested tool %r, which is not a known tool or a configured MCP tool; dropping", tool)
        for tool in [*extra_server_tools, *vetted]:
            if tool not in seen:
                allowed_tools.append(tool)
                seen.add(tool)

    # Effective server set, for the audit trail (the orchestrator also prints
    # this to run.log; logging here covers direct/library callers).
    logger.info("worker mcp servers (effective): %s", sorted(mcp_servers))

    return ClaudeAgentOptions(
        system_prompt=WORKER_SYSTEM_PROMPT,
        cwd=str(project_dir.resolve()),  # canonical: the hook refuses a path through a symlink
        # Empty list = SDK isolation mode: skip user/project/local settings,
        # which is where hooks (and other dev-machine config) live. Without
        # this, the user's SessionStart/Stop/UserPromptSubmit hooks fire in
        # spawned Worker processes and pollute the agent context. This is ONLY
        # hook isolation; it does not gate MCP servers, which are passed
        # explicitly below.
        setting_sources=[],
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        # Confinement to the task worktree, two layers (see each builder): a
        # PreToolUse hook for Write/Edit/MultiEdit/NotebookEdit, and the OS
        # sandbox for Bash. Neither depends on `allowed_tools`.
        env=worker_credential_env(state_path.parent / "worker-env"),
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[build_confinement_hook(project_dir)])]},
        sandbox=build_bash_sandbox(project_dir),
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
