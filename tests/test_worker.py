import json
import os
from pathlib import Path

import pytest

from orchestrator.worker import (
    ConfinementUnavailableError,
    sandboxed_command_argv,
    CROSS_PROVIDER_KEY_DENYLIST,
    DEFAULT_ALLOWED_TOOLS,
    WORKER_MCP_REGISTRY,
    WorkerExtras,
    apply_env_contract,
    build_bash_sandbox,
    build_confinement_hook,
    build_worker_options,
    load_worker_extras,
    resolve_effective_mcp_servers,
)


def test_worker_options_drops_user_settings(tmp_path: Path):
    """setting_sources=[] is the SDK isolation switch that prevents user/project
    settings (and therefore hooks) from being loaded into Worker spawns."""
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert options.setting_sources == []


def test_worker_options_has_state_mcp(tmp_path: Path):
    state_path = tmp_path / "state.json"
    options = build_worker_options(
        state_path=state_path,
        project_dir=tmp_path,
    )
    assert "orchestrator-state" in options.mcp_servers
    assert "mcp__orchestrator-state__update_state" in options.allowed_tools


def test_worker_options_has_secrets_proxy_mcp(tmp_path: Path):
    """Credential-requiring commands route through the secrets-proxy MCP server so
    raw secrets never enter Worker subprocess env or the transcript."""
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert "secrets-proxy" in options.mcp_servers
    server = options.mcp_servers["secrets-proxy"]
    assert server["type"] == "stdio"
    assert server["command"] == "node"
    assert server["args"][0].endswith("/secrets-proxy/mcp/dist/index.js")
    assert "mcp__secrets-proxy__execute_with_secrets" in options.allowed_tools


def test_worker_options_never_puts_proxy_token_in_mcp_config(
    tmp_path: Path, monkeypatch
):
    """No secret must ever appear in the MCP server config, even when some
    stray env var of that shape is set.

    The SDK serializes `mcp_servers` into a `--mcp-config '{...}'` COMMAND LINE
    ARGUMENT. Argv is world-readable, so a token placed here is printed by
    `ps aux` to every process on the machine -- which is how a shared proxy
    token leaked on 2026-08-17 and forced a rotation. There is no shared proxy
    token any more (the MCP client mints its own short-lived token from the
    operator's Infisical machine identity in the Keychain), but this test stays
    as the regression guard: it asserts on the WHOLE serialized config, not
    just one key, so nothing token-shaped can ever regress into it.
    """
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok-from-cc-sh")
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    server = options.mcp_servers["secrets-proxy"]
    assert "PROXY_TOKEN" not in server["env"]
    assert server["env"]["SECRETS_PROXY_URL"]
    # Nothing anywhere in the config may carry the secret, however nested.
    # `default=str` because the in-process state server is an SDK object, not
    # JSON: we only care that the token string appears nowhere in the payload.
    assert "tok-from-cc-sh" not in json.dumps(options.mcp_servers, default=str)
    # The env var itself is still left alone: only Anthropic/provider keys are
    # scrubbed, and other tooling may legitimately read it.
    assert os.environ.get("SECRETS_PROXY_TOKEN") == "tok-from-cc-sh"


def test_worker_options_includes_default_tools(tmp_path: Path):
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    for needed in ["Read", "Edit", "Write", "Bash", "Grep"]:
        assert needed in options.allowed_tools


def test_worker_options_sets_cwd(tmp_path: Path):
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert options.cwd == str(tmp_path)


def test_worker_options_scrubs_anthropic_api_key(tmp_path: Path, monkeypatch):
    """If ANTHROPIC_API_KEY is in env at worker-spawn time, the SDK auto-detects it
    and switches from subscription auth to direct API billing. We don't want that:
    the Worker only needs the key to be referenced in the code it writes, not to be
    present in its own environment. Scrub it so subscription auth always wins."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-should-be-removed")
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-should-be-removed"
    build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_worker_options_scrub_is_noop_when_key_absent(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert "ANTHROPIC_API_KEY" not in os.environ


# --- auth-mode env contract (billing) ---------------------------------------


def test_apply_env_contract_subscription_scrubs_anthropic_and_providers(monkeypatch):
    """Subscription mode removes ANTHROPIC_API_KEY (so the SDK uses the login) and
    always removes foreign provider keys to prevent cross-contamination."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-x")
    removed = apply_env_contract("subscription")
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" in removed
    assert "OPENAI_API_KEY" in removed


def test_apply_env_contract_api_key_keeps_anthropic_scrubs_providers(monkeypatch):
    """api_key mode KEEPS ANTHROPIC_API_KEY (so the SDK bills the metered API) but
    still removes foreign provider keys."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-keep")
    monkeypatch.setenv("GEMINI_API_KEY", "g-x")
    removed = apply_env_contract("api_key")
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-keep"
    assert "GEMINI_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" not in removed
    assert "GEMINI_API_KEY" in removed


def test_apply_env_contract_returns_empty_when_nothing_to_scrub(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", *CROSS_PROVIDER_KEY_DENYLIST):
        monkeypatch.delenv(var, raising=False)
    assert apply_env_contract("subscription") == []


def test_build_worker_options_api_key_mode_keeps_key(tmp_path: Path, monkeypatch):
    """build_worker_options(auth_mode='api_key') must NOT scrub ANTHROPIC_API_KEY."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-keep")
    build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        auth_mode="api_key",
    )
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-keep"


# --- per-goal MCP / allowed-tools extras ------------------------------------


def test_load_worker_extras_empty_when_no_frontmatter():
    extras = load_worker_extras({})
    assert extras.mcp_server_keys == []
    assert extras.allowed_tools == []


def test_load_worker_extras_reads_inline_lists():
    extras = load_worker_extras(
        {
            "worker_mcp_servers": ["context7"],
            "worker_allowed_tools": ["mcp__context7__query-docs", "NotebookEdit"],
        }
    )
    assert extras.mcp_server_keys == ["context7"]
    assert extras.allowed_tools == ["mcp__context7__query-docs", "NotebookEdit"]


def test_load_worker_extras_ignores_non_list_values():
    """A scalar (or anything non-list) degrades to no extras rather than raising."""
    extras = load_worker_extras(
        {"worker_mcp_servers": "context7", "worker_allowed_tools": ""}
    )
    assert extras.mcp_server_keys == []
    assert extras.allowed_tools == []


def test_defaults_preserved_when_no_extras(tmp_path: Path):
    """A goal that declares nothing yields exactly the safe-default Worker."""
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=None,
    )
    assert set(options.mcp_servers) == {"orchestrator-state", "secrets-proxy"}
    assert options.allowed_tools == list(DEFAULT_ALLOWED_TOOLS)


def test_goal_allowed_tools_are_unioned_in(tmp_path: Path):
    extras = WorkerExtras(allowed_tools=["NotebookEdit", "Read"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
    )
    # New tool added, defaults preserved, duplicate ("Read") not re-added.
    assert "NotebookEdit" in options.allowed_tools
    assert options.allowed_tools.count("Read") == 1
    for default in DEFAULT_ALLOWED_TOOLS:
        assert default in options.allowed_tools


def test_goal_mcp_servers_merge_from_registry(tmp_path: Path):
    extras = WorkerExtras(mcp_server_keys=["context7"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
    )
    assert "context7" in options.mcp_servers
    assert options.mcp_servers["context7"]["command"] == "npx"
    # Registry-implied tools are unioned into allowed_tools.
    for tool in WORKER_MCP_REGISTRY["context7"].tools:
        assert tool in options.allowed_tools
    # Defaults still present.
    assert {"orchestrator-state", "secrets-proxy"} <= set(options.mcp_servers)


def test_goal_cannot_drop_default_servers(tmp_path: Path):
    """Naming a default server key is a no-op and cannot replace its config; the
    defaults always remain present and intact."""
    extras = WorkerExtras(mcp_server_keys=["secrets-proxy", "orchestrator-state"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
    )
    assert "secrets-proxy" in options.mcp_servers
    assert "orchestrator-state" in options.mcp_servers
    # secrets-proxy config is the canonical one, not anything a goal supplied.
    assert options.mcp_servers["secrets-proxy"]["command"] == "node"
    assert "mcp__secrets-proxy__execute_with_secrets" in options.allowed_tools
    assert "mcp__orchestrator-state__update_state" in options.allowed_tools


def test_unknown_server_name_handled_safely(tmp_path: Path):
    """An unknown server key is dropped (not injected, not fatal); the Worker
    falls back to the default servers."""
    extras = WorkerExtras(mcp_server_keys=["coolify", "totally-made-up"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
    )
    assert "coolify" not in options.mcp_servers
    assert "totally-made-up" not in options.mcp_servers
    assert set(options.mcp_servers) == {"orchestrator-state", "secrets-proxy"}


# --- brick 3: per-repo MCP-server ceiling (allowed_mcp_servers) --------------


def test_resolve_effective_mcp_servers_none_ceiling_passes_through():
    allowed, dropped = resolve_effective_mcp_servers(["context7", "x"], None)
    assert allowed == ["context7", "x"]
    assert dropped == []


def test_resolve_effective_mcp_servers_drops_out_of_ceiling():
    allowed, dropped = resolve_effective_mcp_servers(["context7", "x"], ["context7"])
    assert allowed == ["context7"]
    assert dropped == ["x"]


def test_resolve_effective_mcp_servers_empty_ceiling_drops_all_extras():
    allowed, dropped = resolve_effective_mcp_servers(["context7"], [])
    assert allowed == []
    assert dropped == ["context7"]


def test_resolve_effective_mcp_servers_defaults_never_dropped():
    """Naming a default server is always allowed even if the ceiling omits it:
    defaults are added unconditionally and can never be removed by the ceiling."""
    allowed, dropped = resolve_effective_mcp_servers(
        ["orchestrator-state", "secrets-proxy", "context7"], ["context7"]
    )
    assert "orchestrator-state" in allowed
    assert "secrets-proxy" in allowed
    assert dropped == []


def test_ceiling_allows_in_ceiling_server(tmp_path: Path):
    extras = WorkerExtras(mcp_server_keys=["context7"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
        allowed_mcp_servers=["context7"],
    )
    assert "context7" in options.mcp_servers
    for tool in WORKER_MCP_REGISTRY["context7"].tools:
        assert tool in options.allowed_tools


def test_ceiling_drops_out_of_ceiling_server(tmp_path: Path):
    """A goal cannot enable a server the operator did not allow for this repo."""
    extras = WorkerExtras(mcp_server_keys=["context7"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
        allowed_mcp_servers=["some-other-server"],  # ceiling that excludes context7
    )
    assert "context7" not in options.mcp_servers
    # registry-implied tools for the dropped server are not unioned in
    for tool in WORKER_MCP_REGISTRY["context7"].tools:
        assert tool not in options.allowed_tools
    # defaults always survive the ceiling
    assert set(options.mcp_servers) == {"orchestrator-state", "secrets-proxy"}


def test_empty_ceiling_drops_all_extras_keeps_defaults(tmp_path: Path):
    extras = WorkerExtras(mcp_server_keys=["context7"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
        allowed_mcp_servers=[],  # operator allows no extra servers on this repo
    )
    assert set(options.mcp_servers) == {"orchestrator-state", "secrets-proxy"}


def test_none_ceiling_is_unchanged_behavior(tmp_path: Path):
    """allowed_mcp_servers=None (repo not in the registry) keeps pre-ceiling
    behavior: a registered goal server is enabled as before."""
    extras = WorkerExtras(mcp_server_keys=["context7"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        extras=extras,
        allowed_mcp_servers=None,
    )
    assert "context7" in options.mcp_servers


def test_worker_options_wire_the_confinement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Confinement must not depend on allowed_tools: the SDK never consults a
    `can_use_tool` callback for a tool that is in allowed_tools (Write, Edit and
    Bash are), which is how the old guard was inert. The options carry a
    PreToolUse hook for the file tools and the OS sandbox for Bash."""
    # conftest swaps in a disabled sandbox so tests that start the CLI run
    # anywhere; this test wants the real settings.
    monkeypatch.setattr("orchestrator.worker.sys.platform", "darwin")
    monkeypatch.setattr("orchestrator.worker.build_bash_sandbox", build_bash_sandbox)
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
    )
    assert options.can_use_tool is None
    matchers = options.hooks["PreToolUse"]
    assert len(matchers) == 1 and len(matchers[0].hooks) == 1
    assert options.sandbox["enabled"] is True
    assert options.sandbox["allowUnsandboxedCommands"] is False
    for tool in ("Write", "Edit", "Bash"):
        assert tool in options.allowed_tools


def _tool_call(tool: str, **tool_input) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


def _denied(result: dict) -> bool:
    out = result.get("hookSpecificOutput") or {}
    return out.get("hookEventName") == "PreToolUse" and out.get("permissionDecision") == "deny"


async def test_confinement_allows_edit_inside_root(tmp_path: Path):
    hook = build_confinement_hook(tmp_path)
    (tmp_path / "file.py").write_text("x")
    assert await hook(_tool_call("Edit", file_path=str(tmp_path / "file.py")), "t1", {}) == {}


@pytest.mark.parametrize("raw", ["notes.md", "sub/notes.md", "./notes.md", "~/notes.md", "~", "evil/x"])
async def test_confinement_refuses_paths_it_cannot_resolve_itself(tmp_path: Path, raw: str):
    """A relative path is resolved by the tool against the session's current
    directory (it moves with `cd`, and a symlink inside can redirect it), and `~`
    is expanded by the tool: the hook cannot tell where either lands, so it asks
    for an absolute path instead of guessing "inside"."""
    hook = build_confinement_hook(tmp_path)
    result = await hook(_tool_call("Write", file_path=raw), "t1", {})
    assert _denied(result)
    assert "absolute path" in result["hookSpecificOutput"]["permissionDecisionReason"]


async def test_confinement_denial_also_stops_the_turn(tmp_path: Path):
    """The old guard interrupted the turn so an escape attempt escalates rather
    than being retried around; the hook keeps that."""
    hook = build_confinement_hook(tmp_path)
    result = await hook(_tool_call("Write", file_path="/etc/hosts"), "t1", {})
    assert result["continue_"] is False
    assert "/etc/hosts" in result["stopReason"]


async def test_confinement_denies_absolute_path_outside_root(tmp_path: Path):
    """The 2026-08-01 bug: a Worker given worktree A edits the main checkout B."""
    root = tmp_path / "worktree-a"
    other = tmp_path / "main-checkout"
    root.mkdir()
    other.mkdir()
    hook = build_confinement_hook(root)
    result = await hook(_tool_call("Edit", file_path=str(other / "src.py")), "t1", {})
    assert _denied(result)
    assert str(other) in result["hookSpecificOutput"]["permissionDecisionReason"]


async def test_confinement_denies_dot_dot_escape(tmp_path: Path):
    root = tmp_path / "worktree-a"
    root.mkdir()
    (tmp_path / "sibling").mkdir()
    hook = build_confinement_hook(root)
    assert _denied(await hook(_tool_call("Write", file_path=str(root / ".." / "sibling" / "leak.txt")), "t1", {}))
    assert _denied(await hook(_tool_call("Write", file_path="../sibling/leak.txt"), "t1", {}))


async def test_confinement_denies_a_symlink_inside_that_points_outside(tmp_path: Path):
    root = tmp_path / "worktree-a"
    outside = tmp_path / "elsewhere"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    hook = build_confinement_hook(root)
    assert _denied(await hook(_tool_call("Write", file_path=str(root / "link" / "leak.txt")), "t1", {}))


@pytest.mark.parametrize(
    ("tool", "key"),
    [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")],
)
async def test_confinement_covers_every_file_tool_and_its_path_key(tmp_path: Path, tool: str, key: str):
    """NotebookEdit names its target `notebook_path`; the old guard read only
    `file_path` and let a notebook write anywhere."""
    root = tmp_path / "worktree-a"
    root.mkdir()
    hook = build_confinement_hook(root)
    assert _denied(await hook(_tool_call(tool, **{key: str(tmp_path / "out.txt")}), "t1", {}))
    assert await hook(_tool_call(tool, **{key: str(root / "in.txt")}), "t1", {}) == {}


async def test_confinement_hook_leaves_other_tools_to_their_own_layer(tmp_path: Path):
    """Bash is confined by the OS sandbox, not parsed here; the hook must pass it
    through rather than pretend to cover it."""
    hook = build_confinement_hook(tmp_path)
    assert await hook(_tool_call("Bash", command="echo x > /somewhere/else"), "t1", {}) == {}
    assert await hook(_tool_call("Edit"), "t1", {}) == {}


def test_bash_sandbox_is_on_and_cannot_be_opted_out_of(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("orchestrator.worker.sys.platform", "darwin")
    monkeypatch.setattr("orchestrator.worker.os.path.exists", lambda _p: True)
    sandbox = build_bash_sandbox()
    assert sandbox["enabled"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["failIfUnavailable"] is True
    # Filesystem confinement only: egress stays as open as it was before.
    assert sandbox["network"] == {"allowedDomains": ["*"]}


def test_bash_sandbox_refuses_an_unsupported_platform(monkeypatch: pytest.MonkeyPatch):
    """No silent downgrade to an unconfined Worker."""
    monkeypatch.setattr("orchestrator.worker.sys.platform", "win32")
    with pytest.raises(ConfinementUnavailableError):
        build_bash_sandbox()


def _fake_probe(returncode: int):
    class Done:
        stderr = b"bwrap: No permissions to create new namespace"

    Done.returncode = returncode
    return lambda *_a, **_k: Done()


def test_bash_sandbox_on_linux_needs_bubblewrap_and_socat(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.shutil.which", lambda _name: None)
    with pytest.raises(ConfinementUnavailableError, match="bwrap and socat"):
        build_bash_sandbox()
    monkeypatch.setattr("orchestrator.worker.shutil.which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    with pytest.raises(ConfinementUnavailableError, match="socat"):
        build_bash_sandbox()
    monkeypatch.setattr("orchestrator.worker.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("orchestrator.worker.subprocess.run", _fake_probe(0))
    assert build_bash_sandbox()["enabled"] is True


def test_bash_sandbox_on_linux_fails_when_user_namespaces_are_forbidden(monkeypatch: pytest.MonkeyPatch):
    """bwrap on PATH is not enough (AppArmor on Ubuntu 24.04): the preflight fails
    when the Worker is built, not at its first Bash call mid-run."""
    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("orchestrator.worker.subprocess.run", _fake_probe(1))
    with pytest.raises(ConfinementUnavailableError, match="user namespace"):
        build_bash_sandbox()


def hook_for(root: Path):
    return build_confinement_hook(root)


async def test_confinement_fails_closed_on_a_path_it_cannot_resolve(tmp_path: Path):
    """A failing hook is non-blocking in the CLI, so an exception inside the check
    must become a refusal, not an allow."""
    hook = build_confinement_hook(tmp_path)
    nul = await hook(_tool_call("Write", file_path=str(tmp_path / "a\0b")), "t1", {})
    assert _denied(nul) and nul["continue_"] is False
    # A symlink loop: Python 3.11 raises RuntimeError from resolve() (refused),
    # 3.13 resolves it leniently to a path that is still inside the root (the
    # tool itself then fails with ELOOP). Either way it cannot reach outside.
    root = tmp_path / "worktree-a"
    root.mkdir()
    loop = root / "loop"
    loop.symlink_to(loop)
    looped = await hook_for(root)(_tool_call("Write", file_path=str(loop / "x")), "t1", {})
    assert _denied(looped) or looped == {}


async def test_confinement_refuses_a_file_with_other_hard_links(tmp_path: Path):
    """One inode under two names: writing the name inside the worktree changes the
    file outside it."""
    root = tmp_path / "worktree-a"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("orig")
    (root / "linked").hardlink_to(outside)
    (root / "plain").write_text("x")
    hook = build_confinement_hook(root)
    assert _denied(await hook(_tool_call("Edit", file_path=str(root / "linked")), "t1", {}))
    assert await hook(_tool_call("Edit", file_path=str(root / "plain")), "t1", {}) == {}


# ---- the command sandbox the Mercury adapter's run_command uses ----


def _git_repo(path: Path) -> Path:
    import subprocess

    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_command_argv_on_linux_protects_a_hooks_dir_that_does_not_exist_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`git init --template=` leaves no hooks dir; a command must not be able to
    create one and plant a hook there."""
    import shutil

    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.require_sandbox_platform", lambda **_k: None)
    work = _git_repo(tmp_path / "work")
    shutil.rmtree(work / ".git" / "hooks")
    argv = sandboxed_command_argv("echo hi", work)
    hooks = str((work / ".git" / "hooks").resolve())
    pairs = [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv) if a == "--ro-bind"]
    sources = [src for src, dst in pairs if dst == hooks]
    assert sources and Path(sources[0]).is_dir() and not any(Path(sources[0]).iterdir())


def test_command_argv_on_linux_does_not_need_socat_but_probes_the_real_flags(monkeypatch: pytest.MonkeyPatch):
    """socat is for the Claude CLI's network proxy; the command sandbox only needs
    bwrap, and its probe must use the flags the real command uses."""
    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.shutil.which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    seen = {}

    def run(argv, **_k):
        seen["argv"] = argv

        class Done:
            returncode = 0
            stderr = b""

        return Done()

    monkeypatch.setattr("orchestrator.worker.subprocess.run", run)
    from orchestrator.worker import _BWRAP_FLAGS, require_sandbox_platform

    require_sandbox_platform(need_socat=False, probe_args=_BWRAP_FLAGS)
    assert "--proc" in seen["argv"] and "--dev" in seen["argv"]
    with pytest.raises(ConfinementUnavailableError, match="socat"):
        require_sandbox_platform()


def test_command_argv_refuses_when_no_sandbox_can_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("orchestrator.worker.sys.platform", "win32")
    with pytest.raises(ConfinementUnavailableError):
        sandboxed_command_argv("echo hi", tmp_path)


@pytest.mark.skipif(
    __import__("sys").platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"),
    reason="runs the real macOS sandbox",
)
def test_command_argv_really_confines_writes_on_macos(tmp_path: Path):
    """Not a mock: the real Seatbelt profile refuses a write outside the worktree
    (in a directory under the home dir, which is not a temp dir) and allows one inside."""
    import shutil
    import subprocess
    import tempfile

    work = tmp_path / "work"
    work.mkdir()
    outside = Path(tempfile.mkdtemp(dir=Path.home(), prefix=".orch-sandbox-test-"))
    try:
        inside = subprocess.run(sandboxed_command_argv(f"echo x > {work.resolve()}/in.txt", work), capture_output=True)
        assert inside.returncode == 0 and (work / "in.txt").exists()
        blocked = subprocess.run(sandboxed_command_argv(f"echo x > {outside}/out.txt", work), capture_output=True)
        assert blocked.returncode != 0 and not (outside / "out.txt").exists()
    finally:
        shutil.rmtree(outside, ignore_errors=True)


@pytest.mark.skipif(
    __import__("sys").platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"),
    reason="runs the real macOS sandbox",
)
def test_command_sandbox_protects_the_git_dir_of_a_plain_repo_on_macos(tmp_path: Path):
    """Not a mock: in a plain repo the .git dir is inside the worktree, so it
    must be protected as an entry too (`mv .git .g` and rebuild), and its hooks
    and config stay read-only, while a commit still works."""
    import subprocess

    work = _git_repo(tmp_path / "work")

    def run(cmd: str):
        return subprocess.run(sandboxed_command_argv(cmd, work), cwd=work, capture_output=True, text=True)

    assert run("mv .git .g").returncode != 0 and (work / ".git").is_dir()
    assert run("echo planted > .git/hooks/pre-commit").returncode != 0
    assert not (work / ".git" / "hooks" / "pre-commit").exists()
    assert run("echo '[core]' >> .git/config").returncode != 0
    ok = run("echo x > f.txt && git add f.txt && git -c user.email=a@b.c -c user.name=p commit -qm probe && git log --format=%s")
    assert ok.returncode == 0 and "probe" in ok.stdout


def _linked_worktree(tmp_path: Path, branch: str = "orchestrator/t") -> tuple[Path, Path]:
    """A main checkout and a linked worktree of it, the way every Worker runs."""
    import subprocess

    base = _git_repo(tmp_path / "base")
    git = ["git", "-c", "user.email=a@b.c", "-c", "user.name=t"]
    subprocess.run([*git, "-C", str(base), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    work = tmp_path / "work"
    subprocess.run([*git, "-C", str(base), "worktree", "add", "-q", "-b", branch, str(work)], check=True)
    return base, work


def test_command_argv_on_macos_in_a_plain_repo_keeps_the_git_dir_an_entry_with_hooks_and_config_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("orchestrator.worker.sys.platform", "darwin")
    monkeypatch.setattr("orchestrator.worker.os.path.exists", lambda _p: True)
    work = _git_repo(tmp_path / "work")
    argv = sandboxed_command_argv("echo hi", work)
    assert argv[:2] == ["/usr/bin/sandbox-exec", "-p"] and argv[3:] == ["/bin/bash", "-c", "echo hi"]
    profile = argv[2]
    assert "(deny file-write*)" in profile and f'(subpath "{work.resolve()}")' in profile
    denied = profile.split("(deny file-write* ")[-1]
    git = (work / ".git").resolve()
    assert f'(literal "{git}")' in denied and f'(subpath "{git / "hooks"}")' in denied and f'(literal "{git / "config"}")' in denied


def test_command_argv_on_macos_in_a_linked_worktree_does_not_let_the_shared_git_dir_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The Worker's own admin dir, its own branch ref and reflog, and a create-only
    object store: nothing else of the main checkout's .git."""
    monkeypatch.setattr("orchestrator.worker.sys.platform", "darwin")
    monkeypatch.setattr("orchestrator.worker.os.path.exists", lambda _p: True)
    base, work = _linked_worktree(tmp_path)
    profile = sandboxed_command_argv("true", work)[2]
    common = (base / ".git").resolve()
    admin = next((common / "worktrees").iterdir()).resolve()
    allowed = profile.split("(deny file-write*)")[1].split("(allow file-write-create")[0]
    assert f'(subpath "{admin}")' in allowed
    assert f'(subpath "{common / "refs" / "heads" / "orchestrator" / "t"}")' in allowed
    # nothing else of the shared dir is in the allow list, in particular not the dir itself
    assert f'(subpath "{common}")' not in allowed
    for name in ("HEAD", "index", "packed-refs", "info", "hooks", "config"):
        assert f'"{common / name}"' not in allowed
    assert f'(subpath "{common / "objects" / "info"}")' in profile.split("file-write-unlink ")[-1]
    # create-only objects: new files and tmp_* files, never an existing object
    assert f'(allow file-write-create (subpath "{common / "objects"}"))' in profile
    assert "file-write-unlink (regex" in profile and "tmp_[^/]*" in profile
    # the worktree's pointer and its link back to the shared dir cannot be rewritten
    denied = profile.split("file-write-unlink ")[-1]  # the final deny rule names every write operation
    assert "(deny file-write* file-write-create" in profile
    assert f'(literal "{work.resolve() / ".git"}")' in denied
    assert f'(literal "{admin / "commondir"}")' in denied and f'(literal "{admin / "gitdir"}")' in denied
    # the keychain daemon and credential files
    assert '(global-name "com.apple.SecurityServer")' in profile
    assert f'(subpath "{Path.home() / ".ssh"}")' in profile.split("(deny file-read* ")[-1]


def test_command_argv_on_linux_binds_only_what_a_linked_worktree_needs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.require_sandbox_platform", lambda **_k: None)
    base, work = _linked_worktree(tmp_path)
    argv = sandboxed_command_argv("echo hi", work)
    assert argv[0] == "bwrap" and argv[1:4] == ["--ro-bind", "/", "/"] and argv[-3:] == ["/bin/bash", "-c", "echo hi"]
    binds = [argv[i + 1] for i, a in enumerate(argv) if a == "--bind"]
    common = (base / ".git").resolve()
    assert str(work.resolve()) in binds
    assert str(common / "objects") in binds and str(common / "refs" / "heads" / "orchestrator") in binds
    assert str(common) not in binds and str(common / "refs" / "heads") not in binds
    ro = [argv[i + 2] for i, a in enumerate(argv) if a == "--ro-bind"]
    assert str(work.resolve() / ".git") in ro


def test_command_argv_on_linux_refuses_a_worktree_branch_without_a_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`feature` lives directly in refs/heads, next to main: it cannot be made
    writable without making main writable, so the command is refused."""
    monkeypatch.setattr("orchestrator.worker.sys.platform", "linux")
    monkeypatch.setattr("orchestrator.worker.require_sandbox_platform", lambda **_k: None)
    _base, work = _linked_worktree(tmp_path, branch="feature")
    with pytest.raises(ConfinementUnavailableError, match="no namespace"):
        sandboxed_command_argv("true", work)


def test_the_claude_sandbox_denies_the_shared_git_dir_path_by_path(tmp_path: Path):
    from orchestrator.worker import _claude_sandbox_filesystem

    base, work = _linked_worktree(tmp_path)
    fs = _claude_sandbox_filesystem(work)
    common = (base / ".git").resolve()
    deny = set(fs["denyWrite"])
    for name in ("HEAD", "packed-refs", "index", "info", "hooks", "config"):
        assert str(common / name) in deny
    assert str(common / "refs" / "heads" / "main") in deny or str(common / "refs" / "heads" / "master") in deny
    assert str(common / "objects" / "info") in deny and str(work.resolve() / ".git") in deny
    own = common / "refs" / "heads" / "orchestrator" / "t"
    assert str(own) not in deny and str(common / "objects") not in deny
    assert str(Path.home() / ".ssh") in fs["denyRead"]


async def test_confinement_hook_applies_the_bash_denylist_and_credentials_commands(tmp_path: Path):
    hook = build_confinement_hook(tmp_path)
    for command in ("rm -rf /", "security find-generic-password -s gh:github.com", "gh auth token", "git credential fill",
                    "git credential-osxkeychain get"):
        result = await hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}, "t1", {})
        assert _denied(result), command
    ok = await hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status && ls"}}, "t1", {})
    assert ok == {}


async def test_confinement_refuses_a_path_through_a_symlink_even_when_it_stays_inside(tmp_path: Path):
    """A symlink inside can be re-pointed between the hook's check and the CLI's
    open; the Worker is given the canonical path instead."""
    root = tmp_path / "worktree-a"
    (root / "real").mkdir(parents=True)
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    hook = build_confinement_hook(root)
    result = await hook(_tool_call("Write", file_path=str(root / "alias" / "f.txt")), "t1", {})
    assert _denied(result) and str(root.resolve() / "real" / "f.txt") in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert await hook(_tool_call("Write", file_path=str(root.resolve() / "real" / "f.txt")), "t1", {}) == {}


def test_path_outside_root_fails_closed_on_a_path_it_cannot_resolve(tmp_path: Path):
    """An unresolvable path (here a NUL byte, which Path.resolve rejects on every
    Python version) is reported as outside, not waved through."""
    from orchestrator.worker import path_outside_root

    assert path_outside_root(str(tmp_path / "a\0b"), tmp_path.resolve()) is not None


def test_a_goal_cannot_add_permission_rules_or_tools_of_unconfigured_servers(tmp_path: Path):
    extras = WorkerExtras(
        allowed_tools=["NotebookEdit", "Bash(git push:*)", "Edit(//Users/me/**)", "mcp__evil__run", "mcp__orchestrator-state__*", "Task"]
    )
    options = build_worker_options(state_path=tmp_path / "s.json", project_dir=tmp_path, extras=extras)
    assert "NotebookEdit" in options.allowed_tools and "mcp__orchestrator-state__*" in options.allowed_tools
    for dropped in ("Bash(git push:*)", "Edit(//Users/me/**)", "mcp__evil__run", "Task"):
        assert dropped not in options.allowed_tools


def test_the_worker_has_no_git_or_gh_credentials_configured(tmp_path: Path):
    from orchestrator.worker import worker_credential_env

    env = worker_credential_env(tmp_path / "worker-env")
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_ASKPASS"] == "/usr/bin/false"
    assert env["GIT_CONFIG_KEY_0"] == "credential.helper" and env["GIT_CONFIG_VALUE_0"] == ""
    assert Path(env["GH_CONFIG_DIR"]).is_dir() and not any(Path(env["GH_CONFIG_DIR"]).iterdir())
    assert "helper" not in Path(env["GIT_CONFIG_GLOBAL"]).read_text()
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"


def test_apply_env_contract_removes_forge_and_cloud_credentials_from_the_worker_environment(monkeypatch: pytest.MonkeyPatch):
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "NPM_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "x")
    removed = apply_env_contract()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "NPM_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        assert name in removed and name not in os.environ
