from pathlib import Path

from orchestrator.config import MarlinProxyConfig
from orchestrator.ledger import read_entries
from orchestrator.marlin_proxy import MarlinDecision
from orchestrator.orchestrator import (
    OrchestratorConfig,
    _load_marlin,
    _record_marlin_decision,
)
from orchestrator.state import State


def _orch_cfg(tmp_path: Path, marlin_persona: Path | None = None) -> OrchestratorConfig:
    return OrchestratorConfig(
        task_id="t1",
        goal_file=tmp_path / "goal.md",
        persona_file=tmp_path / "persona.md",
        project_dir=tmp_path,
        state_dir=tmp_path / "state",
        marlin_persona_file=marlin_persona,
    )


def test_load_marlin_off_when_no_config(tmp_path, monkeypatch):
    # No config.toml -> defaults to off, no persona loaded.
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", str(tmp_path / "cfg"))
    cfg = _orch_cfg(tmp_path)
    mp_config, persona = _load_marlin(cfg, "# Goal\nship it")
    assert mp_config.mode == "off"
    assert persona == ""


def test_load_marlin_forces_off_when_persona_missing(tmp_path, monkeypatch):
    cfg_home = tmp_path / "cfg"
    cfg_home.mkdir()
    (cfg_home / "config.toml").write_text('[marlin_proxy]\nmode = "shadow"\n')
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", str(cfg_home))
    cfg = _orch_cfg(tmp_path, marlin_persona=tmp_path / "absent.md")
    mp_config, persona = _load_marlin(cfg, "# Goal")
    assert mp_config.mode == "off"  # fail safe
    assert persona == ""


def test_load_marlin_loads_persona_when_present(tmp_path, monkeypatch):
    cfg_home = tmp_path / "cfg"
    cfg_home.mkdir()
    (cfg_home / "config.toml").write_text('[marlin_proxy]\nmode = "shadow"\n')
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", str(cfg_home))
    persona_file = tmp_path / "marlin.md"
    persona_file.write_text("be terse")
    cfg = _orch_cfg(tmp_path, marlin_persona=persona_file)
    mp_config, persona = _load_marlin(cfg, "# Goal")
    assert mp_config.mode == "shadow"
    assert persona == "be terse"


def test_load_marlin_applies_per_task_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", str(tmp_path / "cfg"))
    persona_file = tmp_path / "marlin.md"
    persona_file.write_text("p")
    cfg = _orch_cfg(tmp_path, marlin_persona=persona_file)
    goal = "---\nmarlin_proxy: shadow\n---\n# Goal\n"
    mp_config, persona = _load_marlin(cfg, goal)
    assert mp_config.mode == "shadow"  # frontmatter overrode the off default


def test_record_auto_approve_updates_stats_and_ledger(tmp_path):
    config = MarlinProxyConfig(
        ledger_path=tmp_path / "ledger.jsonl",
        notes_path=tmp_path / "notes.md",
    )
    state = State(task_id="t1", goal="g", iteration=3)
    marlin = MarlinDecision(
        choice="auto_approve",
        category="merge_after_verify",
        reason="verify green",
        effective_mode="live",
        proxy_choice="auto_approve",
        executed=True,
    )
    _record_marlin_decision(
        config=config, state=state, marlin=marlin, tokens_in=1000, wall_ms=900, iter_ms=5000
    )
    assert state.autonomy_stats.auto_approved == 1
    assert state.autonomy_stats.decisions_between_escalations == 1
    assert state.autonomy_stats.autonomous_runtime_ms == 5000
    entries = read_entries(config.ledger_path)
    assert len(entries) == 1
    assert entries[0].executed is True
    assert (tmp_path / "notes.md").exists()


def test_record_escalate_resets_streak(tmp_path):
    config = MarlinProxyConfig(
        ledger_path=tmp_path / "ledger.jsonl", notes_path=tmp_path / "notes.md"
    )
    state = State(task_id="t1", goal="g")
    state.autonomy_stats.decisions_between_escalations = 4
    state.autonomy_stats.max_decisions_between_escalations = 4
    marlin = MarlinDecision(
        choice="escalate",
        category="product_decision",
        reason="his taste",
        effective_mode="escalate",
        proxy_choice="escalate",
        executed=False,
    )
    _record_marlin_decision(
        config=config, state=state, marlin=marlin, tokens_in=0, wall_ms=100, iter_ms=200
    )
    assert state.autonomy_stats.escalated == 1
    assert state.autonomy_stats.decisions_between_escalations == 0
    assert state.autonomy_stats.max_decisions_between_escalations == 4  # preserved


def test_record_shadow_logs_would_be_choice(tmp_path):
    config = MarlinProxyConfig(
        ledger_path=tmp_path / "ledger.jsonl", notes_path=tmp_path / "notes.md"
    )
    state = State(task_id="t1", goal="g")
    # shadow: choice is escalate (orchestrator interrupts) but proxy_choice preserved
    marlin = MarlinDecision(
        choice="escalate",
        category="merge_after_verify",
        reason="would approve",
        effective_mode="shadow",
        proxy_choice="auto_approve",
        executed=False,
    )
    _record_marlin_decision(
        config=config, state=state, marlin=marlin, tokens_in=500, wall_ms=800, iter_ms=1000
    )
    entries = read_entries(config.ledger_path)
    assert entries[0].effective_mode == "shadow"
    assert entries[0].proxy_choice == "auto_approve"
    assert entries[0].executed is False
    assert state.autonomy_stats.escalated == 1
