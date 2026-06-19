"""Tests for the orchestrator-level recon call site (run_recon) and the
judge-path invariant: the Worker, Decision Proxy, and Marlin Proxy stay on
Claude regardless of any per-role executor config.
"""

import inspect

from orchestrator import marlin_proxy, proxy, worker
from orchestrator.executor import CLAUDE_MODEL_ID, MERCURY_MODEL_ID
from orchestrator.orchestrator import run_recon
from orchestrator.state import State


def _fake_inception(text: str) -> str:
    import json

    return json.dumps({"choices": [{"message": {"content": text}}]})


async def test_run_recon_defaults_to_claude_and_records_telemetry(tmp_path, monkeypatch):
    """No config => run_recon uses the Claude path (stubbed, no SDK), and writes
    the time_to_verified_result telemetry onto state.last_recon."""
    p = tmp_path / "nope.toml"
    state = State(task_id="t", goal="g")

    async def fake_claude(question):
        return "claude recon: 4 hits"

    monkeypatch.setattr("orchestrator.orchestrator._claude_recon", fake_claude)

    findings = await run_recon("scan for foo", state=state, config_path=p)
    assert findings.executor == "claude"
    assert findings.model_id == CLAUDE_MODEL_ID
    assert findings.findings == "claude recon: 4 hits"
    assert state.last_recon is not None
    assert state.last_recon.executor == "claude"
    assert state.last_recon.ok is True


async def test_run_recon_uses_mercury_when_configured(tmp_path, monkeypatch):
    """recon pinned to Mercury => the non-Claude transport runs, the key never
    touches this process, and telemetry records the mercury executor."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\n')
    state = State(task_id="t", goal="g")
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok-xyz")

    def transport(url, token, body):
        assert body["model"] == MERCURY_MODEL_ID
        return _fake_inception("mercury recon: 1 hit")

    findings = await run_recon("scan", state=state, config_path=p, transport=transport)
    assert findings.executor == "mercury"
    assert findings.findings == "mercury recon: 1 hit"
    assert state.last_recon is not None
    assert state.last_recon.executor == "mercury"


async def test_run_recon_mercury_failure_falls_back_to_claude(tmp_path, monkeypatch):
    """Mercury configured but the transport fails: FAIL LOUD into a Claude recon
    fallback, never a silent skip, never a blocked run."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\n')
    state = State(task_id="t", goal="g")
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok")

    from orchestrator.executor import MercuryUnavailable

    def bad_transport(url, token, body):
        raise MercuryUnavailable("proxy down")

    async def fake_claude(question):
        return "claude fallback"

    monkeypatch.setattr("orchestrator.orchestrator._claude_recon", fake_claude)

    findings = await run_recon("scan", state=state, config_path=p, transport=bad_transport)
    assert findings.executor == "claude"
    assert findings.findings == "claude fallback"
    assert state.last_recon.executor == "claude"


def test_decision_proxy_hardcodes_claude_no_executor_lookup():
    """The Decision Proxy must never resolve a per-role executor: it always runs
    on Claude (the SDK default). Asserting the source does not reach into the
    executor seam keeps the judge path Claude-only."""
    src = inspect.getsource(proxy.run_proxy_decision)
    assert "resolve_executor" not in src
    assert "mercury" not in src.lower()
    assert MERCURY_MODEL_ID not in src


def test_marlin_proxy_hardcodes_claude_no_executor_lookup():
    src = inspect.getsource(marlin_proxy.run_marlin_decision)
    assert "resolve_executor" not in src
    assert "mercury" not in src.lower()
    assert MERCURY_MODEL_ID not in src


def test_worker_options_do_not_route_through_a_foreign_model():
    """build_worker_options never sets a non-Claude model: the Worker stays on
    the Claude SDK session. (The foreign-key denylist already scrubs provider
    keys; the executor seam must not reintroduce one on the Worker path.)"""
    src = inspect.getsource(worker.build_worker_options)
    assert "mercury" not in src.lower()
    assert MERCURY_MODEL_ID not in src
    assert "resolve_executor" not in src
