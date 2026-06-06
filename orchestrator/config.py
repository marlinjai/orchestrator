import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args


MarlinProxyMode = Literal["off", "shadow", "live"]
CategoryMode = Literal["live", "shadow", "escalate"]

MarlinCategory = Literal[
    "merge_after_verify",
    "branch_cleanup",
    "status_fetch",
    "procedural_workflow",
    "scope_change",
    "product_decision",
    "risk_tradeoff",
    "irreversible_ops",
    "context_saturation",
    "unknown",
]

CATEGORIES: tuple[str, ...] = get_args(MarlinCategory)

# Categories whose mode can never be relaxed below "escalate", no matter what
# config or per-task frontmatter says. Mutating live prod / secrets / DNS is
# always Marlin's call.
HARD_ESCALATE_CATEGORIES: frozenset[str] = frozenset({"irreversible_ops"})

DEFAULT_CATEGORY_MODES: dict[str, CategoryMode] = {
    "merge_after_verify": "live",
    "branch_cleanup": "live",
    "status_fetch": "live",
    "procedural_workflow": "shadow",
    "scope_change": "escalate",
    "product_decision": "escalate",
    "risk_tradeoff": "escalate",
    "irreversible_ops": "escalate",
    "context_saturation": "shadow",
    "unknown": "escalate",
}

DEFAULT_CONTEXT_HANDOVER_TOKENS = 80_000
DEFAULT_CONTEXT_SATURATION_TOKENS = 120_000
DEFAULT_PER_DECISION_TIMEOUT_MS = 30_000


def _config_home() -> Path:
    override = os.environ.get("ORCHESTRATOR_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "orchestrator"


def _orchestrator_home() -> Path:
    override = os.environ.get("ORCHESTRATOR_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".orchestrator"


@dataclass
class MarlinProxyConfig:
    mode: MarlinProxyMode = "off"
    persona_path: Path = field(default_factory=lambda: _config_home() / "marlin-persona.md")
    ledger_path: Path = field(default_factory=lambda: _orchestrator_home() / "marlin-proxy-decisions.jsonl")
    notes_path: Path = field(default_factory=lambda: _orchestrator_home() / "marlin-proxy-notes.md")
    kill_switch_path: Path = field(default_factory=lambda: _orchestrator_home() / "marlin-proxy.disabled")
    category_modes: dict[str, CategoryMode] = field(default_factory=lambda: dict(DEFAULT_CATEGORY_MODES))
    context_handover_tokens: int = DEFAULT_CONTEXT_HANDOVER_TOKENS
    context_saturation_tokens: int = DEFAULT_CONTEXT_SATURATION_TOKENS
    per_decision_timeout_ms: int = DEFAULT_PER_DECISION_TIMEOUT_MS

    def effective_mode(self, category: str) -> CategoryMode:
        """Resolve the mode for a category, honoring hard-wired escalation and
        the global off/shadow/live switch. Precedence (most restrictive wins):

        1. Global mode "off" -> everything escalates.
        2. Hard-escalate categories -> always "escalate".
        3. Unknown category -> "escalate".
        4. Global mode "shadow" -> a "live" category is downgraded to "shadow"
           (the global switch is a ceiling on autonomy).
        5. Otherwise the per-category mode.
        """
        if self.mode == "off":
            return "escalate"
        if category in HARD_ESCALATE_CATEGORIES:
            return "escalate"
        if category not in self.category_modes:
            return "escalate"
        cat_mode = self.category_modes[category]
        if self.mode == "shadow" and cat_mode == "live":
            return "shadow"
        return cat_mode


def _coerce_category_modes(raw: dict) -> dict[str, CategoryMode]:
    modes = dict(DEFAULT_CATEGORY_MODES)
    valid_modes = set(get_args(CategoryMode))
    for key, value in raw.items():
        if key not in CATEGORIES:
            raise ValueError(f"unknown marlin_proxy category: {key!r}")
        if value not in valid_modes:
            raise ValueError(f"invalid mode {value!r} for category {key!r}")
        modes[key] = value
    return modes


def load_config(path: Path | None = None) -> MarlinProxyConfig:
    """Load the [marlin_proxy] section from config.toml. Returns defaults
    (mode=off) when the file or section is absent. Raises ValueError on
    malformed values so misconfiguration fails loud, not silent.
    """
    cfg_path = path if path is not None else _config_home() / "config.toml"
    if not cfg_path.exists():
        return MarlinProxyConfig()

    try:
        data = tomllib.loads(cfg_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"config file malformed: {cfg_path}: {e}") from e

    section = data.get("marlin_proxy", {})
    if not isinstance(section, dict):
        raise ValueError(f"[marlin_proxy] must be a table in {cfg_path}")

    cfg = MarlinProxyConfig()

    mode = section.get("mode", "off")
    if mode not in get_args(MarlinProxyMode):
        raise ValueError(f"invalid marlin_proxy mode: {mode!r}")
    cfg.mode = mode

    if "persona_path" in section:
        cfg.persona_path = Path(section["persona_path"]).expanduser()
    if "ledger_path" in section:
        cfg.ledger_path = Path(section["ledger_path"]).expanduser()
    if "notes_path" in section:
        cfg.notes_path = Path(section["notes_path"]).expanduser()
    if "kill_switch_path" in section:
        cfg.kill_switch_path = Path(section["kill_switch_path"]).expanduser()

    categories = section.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError(f"[marlin_proxy.categories] must be a table in {cfg_path}")
    cfg.category_modes = _coerce_category_modes(categories)

    thresholds = section.get("thresholds", {})
    if thresholds:
        if "context_handover_tokens" in thresholds:
            cfg.context_handover_tokens = int(thresholds["context_handover_tokens"])
        if "context_saturation_tokens" in thresholds:
            cfg.context_saturation_tokens = int(thresholds["context_saturation_tokens"])
        if "per_decision_timeout_ms" in thresholds:
            cfg.per_decision_timeout_ms = int(thresholds["per_decision_timeout_ms"])

    return cfg


def apply_task_overrides(cfg: MarlinProxyConfig, frontmatter: dict) -> MarlinProxyConfig:
    """Merge per-task goal-file frontmatter onto a loaded config. Recognizes
    `marlin_proxy` (mode) and `marlin_proxy_categories` (per-category modes).
    Returns a new config; does not mutate the input.
    """
    merged = MarlinProxyConfig(
        mode=cfg.mode,
        persona_path=cfg.persona_path,
        ledger_path=cfg.ledger_path,
        notes_path=cfg.notes_path,
        kill_switch_path=cfg.kill_switch_path,
        category_modes=dict(cfg.category_modes),
        context_handover_tokens=cfg.context_handover_tokens,
        context_saturation_tokens=cfg.context_saturation_tokens,
        per_decision_timeout_ms=cfg.per_decision_timeout_ms,
    )

    task_mode = frontmatter.get("marlin_proxy")
    if task_mode is not None:
        if task_mode not in get_args(MarlinProxyMode):
            raise ValueError(f"invalid per-task marlin_proxy mode: {task_mode!r}")
        merged.mode = task_mode

    task_categories = frontmatter.get("marlin_proxy_categories")
    if task_categories is not None:
        if not isinstance(task_categories, dict):
            raise ValueError("marlin_proxy_categories must be a mapping")
        valid_modes = set(get_args(CategoryMode))
        for key, value in task_categories.items():
            if key not in CATEGORIES:
                raise ValueError(f"unknown per-task category: {key!r}")
            if value not in valid_modes:
                raise ValueError(f"invalid per-task mode {value!r} for {key!r}")
            merged.category_modes[key] = value

    return merged
