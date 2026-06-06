import os
from pathlib import Path

from orchestrator.worker import (
    DEFAULT_ALLOWED_TOOLS,
    WORKER_MCP_REGISTRY,
    WorkerExtras,
    build_worker_options,
    load_worker_extras,
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
    server subprocess env. It is never scrubbed: only ANTHROPIC_API_KEY is."""
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok-from-cc-sh")
    options = build_worker_options(
        state_path=tmp_path / "s.json",
        project_dir=tmp_path,
        denied_bash=[],
    )
    assert options.mcp_servers["secrets-proxy"]["env"]["PROXY_TOKEN"] == "tok-from-cc-sh"
    # token must survive build_worker_options (only ANTHROPIC_API_KEY is scrubbed)
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
