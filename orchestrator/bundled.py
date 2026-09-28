"""Files the orchestrator ships with (the default personas).

The personas live at the repository root (`personas/`), where people read and
edit them, and are also packaged into the wheel as `orchestrator/personas`
(`[tool.hatch.build.targets.wheel.force-include]` in pyproject.toml). An
installed CLI (`uv tool install git+...`, as on hermes) has only the packaged
copy; an editable checkout has only the root copy. Resolving through here works
for both. Before this, every default resolved to `<site-packages>/personas/`,
which does not exist in an install, so `orchestrator start` and `orchestrator
sprint` failed there before the first Worker turn.
"""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def bundled_persona(name: str) -> Path:
    """Path of a shipped persona file (``default.md``, ``marlin.md``)."""
    packaged = _PACKAGE_DIR / "personas" / name
    if packaged.exists():
        return packaged
    return _PACKAGE_DIR.parent / "personas" / name
