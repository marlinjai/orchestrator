from pathlib import Path

from orchestrator.lockcheck import (
    SDK_PACKAGE,
    installed_version,
    lock_drift_warning,
    locked_version,
    repo_lock_path,
)

LOCK = """\
version = 1

[[package]]
name = "claude-agent-sdk"
version = "0.2.121"

[[package]]
name = "mcp"
version = "1.30.0"
"""


def _lock(tmp_path: Path, text: str = LOCK) -> Path:
    path = tmp_path / "uv.lock"
    path.write_text(text)
    return path


def test_locked_version_reads_the_pinned_version_with_any_spelling_of_the_name(tmp_path: Path):
    lock = _lock(tmp_path)
    assert locked_version("claude-agent-sdk", lock) == "0.2.121"
    assert locked_version("Claude_Agent_SDK", lock) == "0.2.121"
    assert locked_version("not-in-the-lock", lock) is None


def test_locked_version_is_none_for_a_missing_or_broken_lock(tmp_path: Path):
    assert locked_version("mcp", tmp_path / "absent.lock") is None
    assert locked_version("mcp", _lock(tmp_path, "this is [not toml")) is None


def test_a_different_installed_sdk_warns_and_names_both_versions_and_the_fix(tmp_path: Path):
    warning = lock_drift_warning(lock_path=_lock(tmp_path), installed="0.2.179")
    assert warning is not None
    assert "0.2.179" in warning and "0.2.121" in warning and SDK_PACKAGE in warning
    assert "scripts/install-tool.sh" in warning


def test_the_locked_sdk_does_not_warn(tmp_path: Path):
    assert lock_drift_warning(lock_path=_lock(tmp_path), installed="0.2.121") is None


def test_nothing_to_compare_stays_silent(tmp_path: Path):
    # no locked version for the package
    assert lock_drift_warning("not-in-the-lock", lock_path=_lock(tmp_path), installed="1.0") is None
    # the package is locked but not installed
    ghost = _lock(tmp_path, LOCK + '\n[[package]]\nname = "zz-not-installed"\nversion = "1.0"\n')
    assert installed_version("zz-not-installed") is None
    assert lock_drift_warning("zz-not-installed", lock_path=ghost) is None
    # no lock beside the package (a plain wheel install): an unreadable lock path
    assert lock_drift_warning(lock_path=tmp_path / "absent.lock", installed="9.9.9") is None


def test_the_repository_lock_pins_the_sdk_and_the_dev_environment_matches_it():
    """In the source checkout the lock exists and the environment `uv sync --frozen`
    built matches it, so a fresh checkout does not warn."""
    lock = repo_lock_path()
    assert lock is not None
    assert locked_version(SDK_PACKAGE, lock) is not None
    assert lock_drift_warning() is None
