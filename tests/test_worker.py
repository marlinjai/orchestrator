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
