"""Tests for the hexagonal executor ports (E2): adapter resolution, the
provider/reasoning_effort profile fields, and a fake WorkerPort turn through
the loop's _run_one_turn seam.

Covers the plan's verification bullets (docs/plans/2026-07-24-hexagonal-executor-ports.md):
- adapter resolution table: anthropic -> ClaudeWorkerAdapter, anything else refused;
- judge-invariant regression: a non-Claude worker without the E4 gate is refused;
- profile validation: provider required for non-default models, never inferred;
  reasoning_effort is Inception-only and enum-checked;
- a fake WorkerSession drives _run_one_turn and yields correct usage mapping.
"""

import pytest

from orchestrator.adapters import resolve_worker_adapter
from orchestrator.adapters.claude_worker import ClaudeWorkerAdapter
from orchestrator.executor import ExecutorProfile, load_executor_config, resolve_executor
from orchestrator.orchestrator import _run_one_turn
from orchestrator.ports import TurnResult, WorkerAdapter, WorkerSession
from pathlib import Path

from orchestrator.state import CallLatency, State

_NO_CONFIG = Path('/nonexistent/orchestrator-config.toml')


# ---- adapter resolution table ----


def test_anthropic_worker_resolves_to_claude_adapter():
    prof = ExecutorProfile(role="worker", model_id="claude-opus-4-8")
    adapter = resolve_worker_adapter(prof, claude_options=object())
    assert isinstance(adapter, ClaudeWorkerAdapter)
    assert isinstance(adapter, WorkerAdapter)  # satisfies the port protocol


def test_non_claude_worker_is_refused_without_a_held_out_verifier(tmp_path):
    """The E4 gate: non-Claude code-writing needs a held-out verifier."""
    prof = ExecutorProfile(role="worker", model_id="mercury-2", provider="inception")
    with pytest.raises(ValueError, match="held-out verifier"):
        resolve_worker_adapter(
            prof, claude_options=object(), work_dir=tmp_path, state_path=tmp_path / "s.json"
        )


def test_non_claude_worker_passes_the_gate_with_a_held_out_verifier(tmp_path):
    from orchestrator.adapters.openai_compat_worker import OpenAICompatWorkerAdapter

    prof = ExecutorProfile(role="worker", model_id="mercury-2", provider="inception")
    adapter = resolve_worker_adapter(
        prof,
        claude_options=object(),
        held_out_verify="pytest held_out/",
        work_dir=tmp_path,
        state_path=tmp_path / "s.json",
    )
    assert isinstance(adapter, OpenAICompatWorkerAdapter)
    assert isinstance(adapter, WorkerAdapter)


def test_provider_without_a_forward_route_is_refused():
    prof = ExecutorProfile(role="worker", model_id="gpt-x", provider="openai")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no worker adapter"):
        resolve_worker_adapter(prof, claude_options=object(), held_out_verify="x")


def test_default_resolution_yields_claude_worker_adapter(tmp_path):
    """No operator config => worker resolves to the Claude adapter, the
    byte-for-byte default path."""
    prof = resolve_executor("worker", config_path=tmp_path / "nope.toml")
    adapter = resolve_worker_adapter(prof, claude_options=object())
    assert isinstance(adapter, ClaudeWorkerAdapter)


# ---- provider / reasoning_effort validation ----


def test_provider_required_for_non_default_model(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\n')
    with pytest.raises(ValueError, match="provider is required"):
        load_executor_config(p)


def test_provider_never_inferred_from_model_id(tmp_path):
    """A mercury-looking model id without an explicit provider fails loud;
    with provider it routes to inception."""
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n')
    prof = resolve_executor("recon", config_path=p)
    assert prof.provider == "inception"
    assert prof.is_mercury is True
    assert prof.is_claude is False


def test_unknown_provider_rejected(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nmodel_id = "gpt-x"\nprovider = "openai"\n')
    with pytest.raises(ValueError, match="provider must be one of"):
        load_executor_config(p)


def test_reasoning_effort_rejected_for_anthropic(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[executors.worker]\nmodel_id = "claude-opus-4-8"\nreasoning_effort = "low"\n'
    )
    with pytest.raises(ValueError, match="Inception-only"):
        load_executor_config(p)


def test_reasoning_effort_enum_checked(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n'
        'reasoning_effort = "turbo"\n'
    )
    with pytest.raises(ValueError, match="reasoning_effort must be one of"):
        load_executor_config(p)


def test_reasoning_effort_accepted_for_inception(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[executors.recon]\nmodel_id = "mercury-2"\nprovider = "inception"\n'
        'reasoning_effort = "instant"\n'
    )
    prof = resolve_executor("recon", config_path=p)
    assert prof.reasoning_effort == "instant"


def test_default_profile_provider_is_anthropic(tmp_path):
    prof = resolve_executor("worker", config_path=tmp_path / "nope.toml")
    assert prof.provider == "anthropic"
    assert prof.reasoning_effort is None
    assert prof.is_claude is True


# ---- fake WorkerSession through the loop seam ----


class _FakeSession:
    """A minimal WorkerSession: returns canned chunks + usage, records calls."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def run_turn(self, user_message: str, *, on_text=None) -> TurnResult:
        self.messages.append(user_message)
        if on_text is not None:
            on_text("hello ")
            on_text("world")
        return TurnResult(
            chunks=["hello ", "world"],
            input_tokens=11,
            output_tokens=7,
            cache_read_tokens=3,
            cache_creation_tokens=2,
            model="fake-model",
            calls=[CallLatency(response_ms=40, tool_ms=15, output_tokens=7)],
        )


async def test_run_one_turn_maps_turn_result_to_iteration_usage():
    session = _FakeSession()
    assert isinstance(session, WorkerSession)  # satisfies the port protocol
    state = State(task_id="t", goal="g", iteration=4)
    chunks, usage, record = await _run_one_turn(
        session=session,
        user_message="do the thing",
        state=state,
        profile=resolve_executor("worker", config_path=_NO_CONFIG),
    )
    assert chunks == ["hello ", "world"]
    assert session.messages == ["do the thing"]
    assert usage.iteration == 4
    assert usage.input_tokens == 11
    assert usage.output_tokens == 7
    assert usage.cache_read_tokens == 3
    assert usage.cache_creation_tokens == 2
    assert usage.model == "fake-model"
    assert usage.worker_ms >= 0
    # E3: the turn also yields a worker ExecutorRecord carrying the adapter's
    # per-call latency rows and their rollups.
    assert record.role == "worker"
    assert record.executor == "claude"
    assert record.provider == "anthropic"
    assert record.model_id == "fake-model"
    assert record.iteration == 4
    assert record.elapsed_ms == usage.worker_ms
    assert record.call_count == 1
    assert record.total_response_ms == 40
    assert record.total_tool_ms == 15
    assert record.total_ttft_ms is None


async def test_run_one_turn_keeps_model_non_null_when_session_omits_it(tmp_path):
    """A session that reports no model must not persist None into the str
    field: the state has to survive a save/load round trip."""
    from orchestrator.state import load_state, save_state

    class _NoModelSession(_FakeSession):
        async def run_turn(self, user_message, *, on_text=None):
            return TurnResult(chunks=["x"])

    state = State(task_id="t", goal="g")
    _, usage, _record = await _run_one_turn(
        session=_NoModelSession(),
        user_message="m",
        state=state,
        profile=resolve_executor("worker", config_path=_NO_CONFIG),
    )
    assert usage.model == ""
    state.usage.append(usage)
    path = tmp_path / "state.json"
    save_state(path, state)
    assert load_state(path).usage[0].model == ""


# ---- model pinning / provider model_id requirements ----


def test_non_default_anthropic_worker_model_is_pinned_on_options():
    from claude_agent_sdk import ClaudeAgentOptions

    opts = ClaudeAgentOptions()
    prof = ExecutorProfile(role="worker", model_id="claude-sonnet-5", provider="anthropic")
    adapter = resolve_worker_adapter(prof, claude_options=opts)
    assert adapter._options.model == "claude-sonnet-5"
    assert opts.model is None  # the caller's options are not mutated


def test_default_worker_model_leaves_options_untouched():
    from claude_agent_sdk import ClaudeAgentOptions

    opts = ClaudeAgentOptions()
    adapter = resolve_worker_adapter(
        ExecutorProfile(role="worker", model_id="claude-opus-4-8"), claude_options=opts
    )
    assert adapter._options is opts


def test_inception_requires_explicit_model_id(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[executors.recon]\nprovider = "inception"\n')
    with pytest.raises(ValueError, match="model_id is required for provider 'inception'"):
        load_executor_config(p)
