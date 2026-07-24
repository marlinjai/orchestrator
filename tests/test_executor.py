"""Tests for the per-role executor seam + the Mercury recon path (executor.py).

Covers the Definition of done:
- default-to-Claude resolution (no config => every role is Claude, unchanged);
- Mercury recon happy path with a MOCKED proxy transport (no network, no key);
- fallback-to-Claude on a missing proxy token / proxy failure / bad response;
- the judges (worker, decision proxy, marlin proxy) stay Claude.
"""

import json

import pytest

from orchestrator import executor as ex
from orchestrator.executor import (
    CLAUDE_MODEL_ID,
    MERCURY_MODEL_ID,
    ExecutorProfile,
    MercuryUnavailable,
    ReconFindings,
    load_executor_config,
    recon,
    record_recon,
    resolve_executor,
    run_mercury_recon,
)
from orchestrator.state import State


# --------------------------------------------------------------------------- #
# default-to-Claude resolution (config-free == single-model behavior)
# --------------------------------------------------------------------------- #


def test_resolve_executor_defaults_every_role_to_claude(tmp_path):
    """With no config file, every role resolves to Claude on subscription auth,
    with no cost ceiling -- byte-for-byte the current single-model behavior."""
    missing = tmp_path / "nope.toml"
    for role in ("worker", "recon", "planner", "anything-else"):
        prof = resolve_executor(role, config_path=missing)
        assert prof.model_id == CLAUDE_MODEL_ID
        assert prof.is_claude is True
        assert prof.is_mercury is False
        assert prof.auth_mode == "subscription"
        assert prof.cost_ceiling_usd is None
        assert prof.role == role


def test_load_executor_config_missing_file_is_empty(tmp_path):
    assert load_executor_config(tmp_path / "nope.toml") == {}


def test_load_executor_config_section_absent_is_empty(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[marlin_proxy]\nmode = "off"\n')
    assert load_executor_config(p) == {}


def test_resolve_executor_config_points_recon_at_mercury(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[executors.recon]
model_id = "mercury"
provider = "inception"
auth_mode = "api_key"
cost_ceiling_usd = 0.50
"""
    )
    prof = resolve_executor("recon", config_path=p)
    assert prof.model_id == MERCURY_MODEL_ID
    assert prof.is_mercury is True
    assert prof.auth_mode == "api_key"
    assert prof.cost_ceiling_usd == 0.50

    # Roles NOT pinned still default to Claude -- a recon override never leaks.
    assert resolve_executor("worker", config_path=p).is_claude is True
    assert resolve_executor("planner", config_path=p).is_claude is True


def test_load_executor_config_rejects_bad_auth_mode(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nauth_mode = "turbo"\n')
    with pytest.raises(ValueError, match="auth_mode"):
        load_executor_config(p)


def test_load_executor_config_rejects_empty_model_id(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = ""\n')
    with pytest.raises(ValueError, match="model_id"):
        load_executor_config(p)


def test_load_executor_config_rejects_non_table_role(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors]\nrecon = "mercury"\n')
    with pytest.raises(ValueError, match="must be a table"):
        load_executor_config(p)


def test_load_executor_config_malformed_toml_fails_loud(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[executors.recon\nmodel_id = ")
    with pytest.raises(ValueError, match="malformed"):
        load_executor_config(p)


def test_nonpositive_cost_ceiling_normalizes_to_none(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[executors.recon]\ncost_ceiling_usd = 0\n")
    assert resolve_executor("recon", config_path=p).cost_ceiling_usd is None


# --------------------------------------------------------------------------- #
# the judges stay Claude (no foreign model on the judge path)
# --------------------------------------------------------------------------- #


def test_judges_stay_claude_even_with_a_mercury_recon_config(tmp_path):
    """A config that points recon at Mercury must NOT move the Worker or either
    Proxy off Claude. Their integrity is the whole trust model."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\nprovider = "inception"\n')
    # Worker (code-writing) and the two judge roles the orchestrator routes by
    # all resolve to Claude regardless of the recon override.
    for judge_role in ("worker", "decision_proxy", "marlin_proxy"):
        prof = resolve_executor(judge_role, config_path=p)
        assert prof.is_claude is True
        assert prof.model_id == CLAUDE_MODEL_ID


# --------------------------------------------------------------------------- #
# Mercury recon happy path (mocked proxy transport; no network, no key)
# --------------------------------------------------------------------------- #


def _fake_inception_response(text: str) -> str:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]})


def test_run_mercury_recon_happy_path_with_mocked_transport():
    seen: dict = {}

    def fake_transport(url, token, body):
        seen["url"] = url
        seen["token"] = token
        seen["body"] = body
        return _fake_inception_response("recon: 3 callers of foo()")

    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    result = run_mercury_recon(
        "who calls foo()?",
        profile=profile,
        transport=fake_transport,
        proxy_token="tok-123",
    )
    assert result.ok is True
    assert result.executor == "mercury"
    assert result.model_id == MERCURY_MODEL_ID
    assert result.findings == "recon: 3 callers of foo()"
    assert result.elapsed_ms >= 0
    # The request the transport saw carries the Mercury model + the question, and
    # nothing about the key (the transport injects it server-side).
    assert seen["body"]["model"] == MERCURY_MODEL_ID
    assert seen["body"]["messages"][-1]["content"] == "who calls foo()?"
    assert "INCEPTION_API_KEY" not in json.dumps(seen["body"])


def test_run_mercury_recon_raises_without_proxy_token(monkeypatch):
    monkeypatch.delenv("SECRETS_PROXY_TOKEN", raising=False)
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="token absent"):
        run_mercury_recon("q", profile=profile, transport=lambda *a: "x")


def test_run_mercury_recon_raises_on_non_json_response():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="not JSON"):
        run_mercury_recon(
            "q", profile=profile, transport=lambda *a: "<html>oops</html>", proxy_token="t"
        )


def test_run_mercury_recon_raises_on_empty_completion():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="empty"):
        run_mercury_recon(
            "q",
            profile=profile,
            transport=lambda *a: _fake_inception_response("   "),
            proxy_token="t",
        )


def test_run_mercury_recon_raises_on_missing_content_field():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="content"):
        run_mercury_recon(
            "q",
            profile=profile,
            transport=lambda *a: json.dumps({"choices": []}),
            proxy_token="t",
        )


def test_curl_passes_body_on_stdin_and_references_only_the_env_key():
    """The Inception curl references the key only as the proxy-injected env var,
    and carries the request body on stdin (heredoc), so neither the key nor a
    crafted question can break out into the shell command."""
    body = {"model": "mercury", "messages": [{"role": "user", "content": "hi"}]}
    cmd = ex._build_inception_curl(body)
    assert "$INCEPTION_API_KEY" in cmd
    assert "--data-binary @-" in cmd
    assert "ORCH_MERCURY_EOF" in cmd
    assert json.dumps(body) in cmd


# --------------------------------------------------------------------------- #
# recon(): one call site, with fallback-to-Claude
# --------------------------------------------------------------------------- #


def test_recon_defaults_to_claude_when_no_config(tmp_path):
    """No config => recon resolves to Claude and uses the injected claude_recon,
    never the Mercury path."""
    p = tmp_path / "nope.toml"
    calls: list[str] = []

    def claude(q):
        calls.append(q)
        return "claude says: 2 callers"

    result = recon("who calls foo()?", config_path=p, claude_recon=claude)
    assert result.executor == "claude"
    assert result.model_id == CLAUDE_MODEL_ID
    assert result.findings == "claude says: 2 callers"
    assert result.ok is True
    assert calls == ["who calls foo()?"]


def test_recon_uses_mercury_when_configured(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\nprovider = "inception"\n')

    def transport(url, token, body):
        return _fake_inception_response("mercury findings")

    result = recon(
        "q", config_path=p, transport=transport, proxy_token="tok", claude_recon=lambda q: "x"
    )
    assert result.executor == "mercury"
    assert result.findings == "mercury findings"


def test_recon_falls_back_to_claude_when_mercury_unavailable(tmp_path):
    """Mercury configured but the proxy token is absent: FAIL LOUD into a Claude
    recon fallback, never a silent skip, never a blocked run."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\nprovider = "inception"\n')

    def boom(url, token, body):  # would be the proxy call
        raise AssertionError("transport should not be reached without a token")

    result = recon(
        "q",
        config_path=p,
        transport=boom,
        proxy_token=None,  # no token => MercuryUnavailable => Claude fallback
        claude_recon=lambda q: "claude fallback findings",
    )
    assert result.executor == "claude"
    assert result.findings == "claude fallback findings"
    assert result.ok is True


def test_recon_falls_back_to_claude_on_transport_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury"\nprovider = "inception"\n')

    def bad_transport(url, token, body):
        raise MercuryUnavailable("proxy 502")

    result = recon(
        "q",
        config_path=p,
        transport=bad_transport,
        proxy_token="tok",
        claude_recon=lambda q: "fell back",
    )
    assert result.executor == "claude"
    assert result.findings == "fell back"


def test_recon_without_claude_callable_returns_not_run(tmp_path):
    """Library/test use with no Claude wiring degrades loudly (ok=False) rather
    than raising or pretending success."""
    p = tmp_path / "nope.toml"
    result = recon("q", config_path=p, claude_recon=None)
    assert result.ok is False
    assert result.executor == "claude"
    assert "no claude_recon" in (result.error or "")


# --------------------------------------------------------------------------- #
# time_to_verified_result telemetry (logged, never gated)
# --------------------------------------------------------------------------- #


def test_record_recon_writes_logged_telemetry_to_state():
    state = State(task_id="t", goal="g")
    findings = ReconFindings(
        question="q",
        findings="f",
        executor="mercury",
        model_id=MERCURY_MODEL_ID,
        elapsed_ms=1234,
        ok=True,
    )
    record_recon(state, findings)
    assert state.last_recon is not None
    assert state.last_recon.executor == "mercury"
    assert state.last_recon.model_id == MERCURY_MODEL_ID
    assert state.last_recon.elapsed_ms == 1234
    assert state.last_recon.ok is True


def test_record_recon_survives_round_trip(tmp_path):
    from orchestrator.state import load_state, save_state

    state = State(task_id="t", goal="g")
    record_recon(
        state,
        ReconFindings(
            question="q",
            findings="f",
            executor="claude",
            model_id=CLAUDE_MODEL_ID,
            elapsed_ms=5,
            ok=True,
        ),
    )
    path = tmp_path / "state.json"
    save_state(path, state)
    reloaded = load_state(path)
    assert reloaded.last_recon is not None
    assert reloaded.last_recon.executor == "claude"
    assert reloaded.last_recon.elapsed_ms == 5
