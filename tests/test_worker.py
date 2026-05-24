import os
from pathlib import Path

from orchestrator.worker import build_worker_options


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
