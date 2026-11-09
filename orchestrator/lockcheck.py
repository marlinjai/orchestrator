"""Warn when the installed claude-agent-sdk is not the version in uv.lock.

The Worker's confinement (the PreToolUse hook, the Bash sandbox settings, the
shared-git deny lists) is proved with `scripts/prove_confinement.py` against the
claude-agent-sdk version `uv.lock` pins. `uv tool install --editable .` ignores
the lockfile and resolves fresh, which once installed a newer SDK than the one
proved; `scripts/install-tool.sh` installs the locked versions, and this check
says so at the start of a run when the two differ.

A version comparison only: no network, no installing. It needs `uv.lock`, which
exists next to the package in a source or editable install; with none (a plain
wheel install) there is nothing to compare and it stays silent.
"""

import importlib.metadata
import tomllib
from pathlib import Path

SDK_PACKAGE = "claude-agent-sdk"


def repo_lock_path() -> Path | None:
    """`uv.lock` beside the package, when this is a source or editable install."""
    path = Path(__file__).resolve().parent.parent / "uv.lock"
    return path if path.is_file() else None


def locked_version(package: str, lock_path: Path) -> str | None:
    """The version `lock_path` pins for ``package``, or None when it is not there
    or the lock cannot be read."""
    try:
        data = tomllib.loads(lock_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    wanted = package.lower().replace("_", "-")
    for entry in data.get("package", []):
        if str(entry.get("name", "")).lower().replace("_", "-") == wanted:
            return entry.get("version")
    return None


def installed_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def lock_drift_warning(
    package: str = SDK_PACKAGE,
    *,
    lock_path: Path | None = None,
    installed: str | None = None,
) -> str | None:
    """A warning when the installed ``package`` differs from uv.lock, else None
    (also None when there is no lock, no locked version or no installed version:
    nothing to compare)."""
    lock = lock_path if lock_path is not None else repo_lock_path()
    if lock is None:
        return None
    locked = locked_version(package, lock)
    have = installed if installed is not None else installed_version(package)
    if locked is None or have is None or locked == have:
        return None
    return (
        f"installed {package} {have} differs from uv.lock {locked}: the Worker confinement is proved "
        f"only against the locked version. Reinstall the tool with scripts/install-tool.sh."
    )
