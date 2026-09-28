"""The default personas must ship with the package.

Regression (2026-09-29, the first M9 sprint on hermes): the wheel contained only
the `orchestrator` package, while every default persona path pointed at the
repository root, so an installed CLI (`uv tool install git+...`) failed with
FileNotFoundError before the first Worker turn, for `start` and `sprint` alike.
"""

import importlib
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from orchestrator import bundled
from orchestrator.bundled import bundled_persona

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["default.md", "marlin.md"])
def test_personas_resolve_in_a_checkout(name):
    assert bundled_persona(name).read_text().strip()


def test_personas_resolve_from_an_installed_package_layout(tmp_path, monkeypatch):
    """An install has the packaged copy and no repository root next to it."""
    pkg = tmp_path / "site-packages" / "orchestrator"
    (pkg / "personas").mkdir(parents=True)
    (pkg / "personas" / "default.md").write_text("installed persona")
    monkeypatch.setattr(bundled, "_PACKAGE_DIR", pkg)
    assert bundled_persona("default.md").read_text() == "installed persona"


def test_cli_uses_installed_persona_defaults(tmp_path, monkeypatch):
    """`start` and `sprint` bind their persona defaults at import time, so the
    installed layout must be in place before `orchestrator.main` is (re)loaded."""
    pkg = tmp_path / "site-packages" / "orchestrator"
    (pkg / "personas").mkdir(parents=True)
    (pkg / "personas" / "default.md").write_text("installed default")
    (pkg / "personas" / "marlin.md").write_text("installed marlin")
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path / "home"))

    import orchestrator.main as main_mod
    import orchestrator.sprint as sprint_mod

    captured = {}

    async def fake_start(cfg):
        captured["start"] = cfg

    async def fake_sprint(cfg, **_kwargs):
        captured["sprint"] = cfg
        return SimpleNamespace(status="completed")

    goal = tmp_path / "goal.md"
    goal.write_text("goal")
    monkeypatch.setattr(bundled, "_PACKAGE_DIR", pkg)
    try:
        main = importlib.reload(main_mod)
        monkeypatch.setattr(main, "run_orchestrator", fake_start)
        monkeypatch.setattr(sprint_mod, "run_sprint", fake_sprint)
        runner = CliRunner()
        for command in ("start", "sprint"):
            result = runner.invoke(
                main.app, [command, "--goal", str(goal), "--project", str(tmp_path)]
            )
            assert result.exit_code == 0, result.output
    finally:
        monkeypatch.undo()
        importlib.reload(main_mod)

    assert set(captured) == {"start", "sprint"}
    for cfg in captured.values():
        assert cfg.persona_file == pkg / "personas" / "default.md"
        assert cfg.marlin_persona_file == pkg / "personas" / "marlin.md"


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to build the wheel")
def test_the_wheel_contains_the_personas(tmp_path):
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(REPO)],
        check=True,
        capture_output=True,
    )
    (wheel,) = tmp_path.glob("*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "orchestrator/personas/default.md" in names
    assert "orchestrator/personas/marlin.md" in names
