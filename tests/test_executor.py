"""Tests for the per-role executor seam + the Mercury recon path (executor.py).

Covers the Definition of done:
- default-to-Claude resolution (no config => every role is Claude, unchanged);
- Mercury recon happy path with a MOCKED proxy transport (no network, no key);
- fallback-to-Claude on a missing proxy token / proxy failure / bad response;
- the judges (worker, decision proxy, marlin proxy) stay Claude.
"""

import json
import shutil

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

# These tests start a real `node`; skip them on a host without one.
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")


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
model_id = "mercury-2"
provider = "inception"
auth_mode = "api_key"
"""
    )
    prof = resolve_executor("recon", config_path=p)
    assert prof.model_id == MERCURY_MODEL_ID
    assert prof.is_mercury is True
    assert prof.auth_mode == "api_key"

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


def test_removed_cost_ceiling_is_rejected_loudly(tmp_path):
    """cost_ceiling_usd was parsed but never enforced; it is now refused at load
    so an operator never believes a per-role ceiling is protecting them."""
    p = tmp_path / "config.toml"
    p.write_text("[executors.recon]\ncost_ceiling_usd = 0.50\n")
    with pytest.raises(ValueError, match="--max-cost-usd"):
        load_executor_config(p)


# --------------------------------------------------------------------------- #
# the judges stay Claude (no foreign model on the judge path)
# --------------------------------------------------------------------------- #


def test_judges_stay_claude_even_with_a_mercury_recon_config(tmp_path):
    """A config that points recon at Mercury must NOT move the Worker or either
    Proxy off Claude. Their integrity is the whole trust model."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n')
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

    def fake_transport(cli_path, body):
        seen["cli_path"] = cli_path
        seen["body"] = body
        return _fake_inception_response("recon: 3 callers of foo()")

    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    result = run_mercury_recon(
        "who calls foo()?",
        profile=profile,
        transport=fake_transport,
        cli_path="fake-secrets-proxy-cli.js",
    )
    assert result.ok is True
    assert result.executor == "mercury"
    assert result.model_id == MERCURY_MODEL_ID
    assert result.findings == "recon: 3 callers of foo()"
    assert result.elapsed_ms >= 0
    assert seen["cli_path"] == "fake-secrets-proxy-cli.js"
    # The request the transport saw carries the Mercury model + the question, and
    # nothing about the key (the CLI/proxy inject it server-side).
    assert seen["body"]["model"] == MERCURY_MODEL_ID
    assert seen["body"]["messages"][-1]["content"] == "who calls foo()?"
    assert "INCEPTION_API_KEY" not in json.dumps(seen["body"])


def test_run_mercury_recon_raises_without_cli(monkeypatch):
    """No secrets-proxy-call CLI resolvable (and none passed explicitly):
    availability is simply 'the CLI exists', so this fails loud."""
    monkeypatch.setattr(ex, "resolve_proxy_cli", lambda: None)
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="CLI not found"):
        run_mercury_recon("q", profile=profile, transport=lambda *a: "x")


def test_run_mercury_recon_raises_on_non_json_response():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="not JSON"):
        run_mercury_recon(
            "q",
            profile=profile,
            transport=lambda *a: "<html>oops</html>",
            cli_path="fake-cli.js",
        )


def test_run_mercury_recon_raises_on_empty_completion():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="empty"):
        run_mercury_recon(
            "q",
            profile=profile,
            transport=lambda *a: _fake_inception_response("   "),
            cli_path="fake-cli.js",
        )


def test_run_mercury_recon_raises_on_missing_content_field():
    profile = ExecutorProfile(role="recon", model_id=MERCURY_MODEL_ID)
    with pytest.raises(MercuryUnavailable, match="content"):
        run_mercury_recon(
            "q",
            profile=profile,
            transport=lambda *a: json.dumps({"choices": []}),
            cli_path="fake-cli.js",
        )


def _write_node_stub(path, *, stdout: str, exit_code: int = 0, stderr: str = ""):
    """A tiny node script standing in for the secrets-proxy-call CLI: echoes its
    own argv + stdin to a trace file (so the test can assert on the call), then
    writes the scripted stdout/stderr and exits with the scripted code."""
    trace = path.with_suffix(".trace")
    script = f"""#!/usr/bin/env node
const fs = require("fs");
const stdin = fs.readFileSync(0, "utf8");
fs.writeFileSync({json.dumps(str(trace))}, "ARGV=" + process.argv.slice(2).join(",") + "\\n" + stdin);
process.stdout.write({json.dumps(stdout)});
process.stderr.write({json.dumps(stderr)});
process.exit({exit_code});
"""
    path.write_text(script)
    return trace


@needs_node
def test_provider_forward_pipes_body_into_the_cli_and_returns_stdout(tmp_path):
    """The transport shells out to `node <cli> forward <route>` with the chat
    body on stdin and returns stdout verbatim; no token, no upstream URL, no
    Infisical coordinates cross this boundary."""
    cli = tmp_path / "cli.js"
    trace = _write_node_stub(cli, stdout=_fake_inception_response("ok"))
    body = {"model": MERCURY_MODEL_ID, "messages": [{"role": "user", "content": "hi"}]}
    raw = ex._proxy_provider_forward(str(cli), body)
    assert json.loads(raw)["choices"][0]["message"]["content"] == "ok"
    call = trace.read_text()
    assert call.startswith(f"ARGV=forward,{ex.INCEPTION_FORWARD_ROUTE}\n")
    assert json.loads(call.split("\n", 1)[1]) == body
    for forbidden in ("projectId", "INCEPTION_API_KEY", "api.inceptionlabs.ai", "X-Proxy-Token"):
        assert forbidden not in call


@needs_node
def test_provider_forward_nonzero_exit_is_mercury_unavailable(tmp_path):
    """A non-2xx from the proxy (surfaced by the CLI's non-zero exit) fails
    loud with the CLI's stderr reason, so recon falls back to Claude visibly."""
    cli = tmp_path / "cli.js"
    _write_node_stub(cli, stdout="", exit_code=1, stderr="502: could not resolve the provider key")
    with pytest.raises(MercuryUnavailable, match="exited 1.*could not resolve"):
        ex._proxy_provider_forward(str(cli), {"model": "m"})


@needs_node
def test_provider_forward_missing_cli_file_is_mercury_unavailable(tmp_path):
    """node itself runs fine but cannot find the script: a non-zero exit,
    surfaced the same way as any other CLI failure."""
    with pytest.raises(MercuryUnavailable, match="exited 1"):
        ex._proxy_provider_forward(str(tmp_path / "nope.js"), {"model": "m"})


def test_provider_forward_missing_node_is_mercury_unavailable(monkeypatch, tmp_path):
    """node itself is not runnable (renamed away, missing PATH entry, ...):
    subprocess.run raises OSError, which is caught and re-raised loud."""

    def boom(*a, **k):
        raise FileNotFoundError("node not found")

    monkeypatch.setattr(ex.subprocess, "run", boom)
    with pytest.raises(MercuryUnavailable, match="failed to run"):
        ex._proxy_provider_forward(str(tmp_path / "cli.js"), {"model": "m"})


def test_resolve_proxy_cli_missing_file_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv(ex.PROXY_CLI_ENV, str(tmp_path / "nope" / "cli.js"))
    assert ex.resolve_proxy_cli() is None


def test_resolve_proxy_cli_finds_the_built_cli(monkeypatch, tmp_path):
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(ex.PROXY_CLI_ENV, str(cli))
    assert ex.resolve_proxy_cli() == cli


def test_resolve_proxy_cli_none_without_node(monkeypatch, tmp_path):
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(ex.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(ex.shutil, "which", lambda name: None)
    assert ex.resolve_proxy_cli() is None


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
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n')

    def transport(cli_path, body):
        return _fake_inception_response("mercury findings")

    result = recon(
        "q", config_path=p, transport=transport, cli_path="fake-cli.js", claude_recon=lambda q: "x"
    )
    assert result.executor == "mercury"
    assert result.findings == "mercury findings"


def test_recon_falls_back_to_claude_when_mercury_unavailable(monkeypatch, tmp_path):
    """Mercury configured but the secrets-proxy-call CLI is not resolvable:
    FAIL LOUD into a Claude recon fallback, never a silent skip, never a
    blocked run."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n')
    monkeypatch.setattr(ex, "resolve_proxy_cli", lambda: None)

    def boom(cli_path, body):  # would be the proxy call
        raise AssertionError("transport should not be reached without a resolvable CLI")

    result = recon(
        "q",
        config_path=p,
        transport=boom,
        cli_path=None,  # no CLI resolvable => MercuryUnavailable => Claude fallback
        claude_recon=lambda q: "claude fallback findings",
    )
    assert result.executor == "claude"
    assert result.findings == "claude fallback findings"
    assert result.ok is True


def test_recon_falls_back_to_claude_on_transport_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n')

    def bad_transport(cli_path, body):
        raise MercuryUnavailable("proxy 502")

    result = recon(
        "q",
        config_path=p,
        transport=bad_transport,
        cli_path="fake-cli.js",
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
