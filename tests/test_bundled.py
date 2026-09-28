"""The default personas must ship with the package.

Regression (2026-09-29, the first M9 sprint on hermes): the wheel contained only
the `orchestrator` package, while every default persona path pointed at the
repository root, so an installed CLI (`uv tool install git+...`) failed with
FileNotFoundError before the first Worker turn, for `start` and `sprint` alike.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

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
