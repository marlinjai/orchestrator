from pathlib import Path
from typer.testing import CliRunner
from orchestrator.main import app


runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout
    assert "status" in result.stdout
    assert "stop" in result.stdout
    assert "logs" in result.stdout


def test_status_missing_task(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    result = runner.invoke(app, ["status", "--task-id", "nonexistent"])
    assert result.exit_code != 0


def test_stop_creates_kill_switch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    task_dir = tmp_path / "tasks" / "abc"
    task_dir.mkdir(parents=True)
    result = runner.invoke(app, ["stop", "--task-id", "abc"])
    assert result.exit_code == 0
    assert (task_dir / "STOP").exists()


def test_status_shows_state(tmp_path: Path, monkeypatch):
    from orchestrator.state import State, save_state
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    task_dir = tmp_path / "tasks" / "abc"
    task_dir.mkdir(parents=True)
    save_state(task_dir / "state.json", State(task_id="abc", goal="g", iteration=4))
    result = runner.invoke(app, ["status", "--task-id", "abc"])
    assert result.exit_code == 0
    assert "abc" in result.stdout
    assert "4" in result.stdout
    # fleet-wide usage line is always surfaced
    assert "global_today" in result.stdout


def test_status_surfaces_tamper_and_confidence(tmp_path: Path, monkeypatch):
    from orchestrator.state import State, save_state
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    task_dir = tmp_path / "tasks" / "abc"
    task_dir.mkdir(parents=True)
    save_state(
        task_dir / "state.json",
        State(
            task_id="abc",
            goal="g",
            tamper_paths=["tests/test_x.py"],
            confidence=0.6,
        ),
    )
    result = runner.invoke(app, ["status", "--task-id", "abc"])
    assert result.exit_code == 0
    assert "tamper_paths" in result.stdout
    assert "confidence" in result.stdout
