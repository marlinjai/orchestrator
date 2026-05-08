import os
from pathlib import Path
import pytest
from orchestrator.worker import build_worker_options, build_worker_env


def test_worker_env_disables_hooks():
    env = build_worker_env()
    assert env.get("CLAUDE_DISABLE_HOOKS") == "1"


def test_worker_env_inherits_path():
    env = build_worker_env()
    assert "PATH" in env


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
