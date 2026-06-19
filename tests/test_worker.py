import os
from pathlib import Path

from orchestrator.worker import (
    CROSS_PROVIDER_KEY_DENYLIST,
    DEFAULT_ALLOWED_TOOLS,
    WORKER_MCP_REGISTRY,
    WorkerExtras,
    apply_env_contract,
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
        denied_bash=[],
    )
    assert options.setting_sources == []


def test_worker_options_has_state_mcp(tmp_path: Path):
    state_path = tmp_path / "state.json"
    options = build_worker_options(
        state_path=state_path,
        project_dir=tmp_path,
        denied_bash=["rm -rf"],
    )
    assert "orchestrator-state" in options.mcp_servers
    assert "mcp__orchestrator-state__update_state" in options.allowed_tools


def test_worker_options_has_secrets_proxy_mcp(tmp_path: Path):
    """Credential-requiring commands route through the secrets-proxy MCP server so
    raw secrets never enter Worker subprocess env or the transcript."""
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
    )
    assert "secrets-proxy" in options.mcp_servers
    server = options.mcp_servers["secrets-proxy"]
    assert server["type"] == "stdio"
    assert server["command"] == "node"
    assert server["args"][0].endswith("/secrets-proxy/mcp/dist/index.js")
    assert "mcp__secrets-proxy__execute_with_secrets" in options.allowed_tools


def test_worker_options_secrets_proxy_token_from_env(tmp_path: Path, monkeypatch):
    """The proxy token passes through from env (injected by cc.sh) into the MCP
    server subprocess env. The env contract only scrubs Anthropic auth and foreign
    provider keys, so SECRETS_PROXY_TOKEN is left intact."""
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok-from-cc-sh")
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
    )
    assert options.mcp_servers["secrets-proxy"]["env"]["PROXY_TOKEN"] == "tok-from-cc-sh"
    # token must survive build_worker_options (it is not an auth/provider key)
    assert os.environ.get("SECRETS_PROXY_TOKEN") == "tok-from-cc-sh"


def test_worker_options_secrets_proxy_token_defaults_empty(tmp_path: Path, monkeypatch):
    """When the token is absent, env carries an empty string. The MCP server will
    exit(1) at startup and the tool degrades to unavailable; the orchestrator
    itself stays up."""
    monkeypatch.delenv("SECRETS_PROXY_TOKEN", raising=False)
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
    )
    assert options.mcp_servers["secrets-proxy"]["env"]["PROXY_TOKEN"] == ""


def test_worker_options_includes_default_tools(tmp_path: Path):
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
    )
    for needed in ["Read", "Edit", "Write", "Bash", "Grep"]:
        assert needed in options.allowed_tools


def test_worker_options_sets_cwd(tmp_path: Path):
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
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
        denied_bash=[],
    )
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_worker_options_scrub_is_noop_when_key_absent(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
        extras=None,
    )
    assert set(options.mcp_servers) == {"orchestrator-state", "secrets-proxy"}
    assert options.allowed_tools == list(DEFAULT_ALLOWED_TOOLS)


def test_goal_allowed_tools_are_unioned_in(tmp_path: Path):
    extras = WorkerExtras(allowed_tools=["NotebookEdit", "Read"])
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
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
        denied_bash=[],
        extras=extras,
        allowed_mcp_servers=None,
    )
    assert "context7" in options.mcp_servers
