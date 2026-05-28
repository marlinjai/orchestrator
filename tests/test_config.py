import pytest

from orchestrator.config import (
    DEFAULT_CATEGORY_MODES,
    MarlinProxyConfig,
    apply_task_overrides,
    load_config,
)


def test_load_config_missing_file_returns_defaults_off(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.mode == "off"
    assert cfg.category_modes == DEFAULT_CATEGORY_MODES


def test_load_config_parses_section(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[marlin_proxy]
mode = "live"

[marlin_proxy.categories]
merge_after_verify = "live"
procedural_workflow = "live"

[marlin_proxy.thresholds]
context_saturation_tokens = 90000
"""
    )
    cfg = load_config(p)
    assert cfg.mode == "live"
    assert cfg.category_modes["procedural_workflow"] == "live"
    assert cfg.context_saturation_tokens == 90000


def test_load_config_rejects_unknown_category(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[marlin_proxy.categories]\nbogus = "live"\n')
    with pytest.raises(ValueError, match="unknown marlin_proxy category"):
        load_config(p)


def test_load_config_rejects_bad_mode(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[marlin_proxy]\nmode = "turbo"\n')
    with pytest.raises(ValueError, match="invalid marlin_proxy mode"):
        load_config(p)


def test_effective_mode_off_escalates_everything():
    cfg = MarlinProxyConfig(mode="off")
    assert cfg.effective_mode("merge_after_verify") == "escalate"


def test_effective_mode_irreversible_always_escalates_even_if_live():
    cfg = MarlinProxyConfig(mode="live")
    cfg.category_modes["irreversible_ops"] = "live"  # try to relax it
    assert cfg.effective_mode("irreversible_ops") == "escalate"


def test_effective_mode_global_shadow_downgrades_live_category():
    cfg = MarlinProxyConfig(mode="shadow")
    cfg.category_modes["merge_after_verify"] = "live"
    assert cfg.effective_mode("merge_after_verify") == "shadow"


def test_effective_mode_live_category_in_live_mode():
    cfg = MarlinProxyConfig(mode="live")
    assert cfg.effective_mode("merge_after_verify") == "live"


def test_effective_mode_unknown_category_escalates():
    cfg = MarlinProxyConfig(mode="live")
    assert cfg.effective_mode("not_a_category") == "escalate"


def test_apply_task_overrides_does_not_mutate_input():
    cfg = MarlinProxyConfig(mode="shadow")
    merged = apply_task_overrides(cfg, {"marlin_proxy": "live"})
    assert cfg.mode == "shadow"
    assert merged.mode == "live"


def test_apply_task_overrides_category():
    cfg = MarlinProxyConfig(mode="live")
    merged = apply_task_overrides(
        cfg, {"marlin_proxy_categories": {"branch_cleanup": "shadow"}}
    )
    assert merged.category_modes["branch_cleanup"] == "shadow"
    assert cfg.category_modes["branch_cleanup"] == "live"


def test_apply_task_overrides_rejects_bad_category():
    cfg = MarlinProxyConfig()
    with pytest.raises(ValueError, match="unknown per-task category"):
        apply_task_overrides(cfg, {"marlin_proxy_categories": {"nope": "live"}})
