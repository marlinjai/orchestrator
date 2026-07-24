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
from orchestrator.state import State


# ---- adapter resolution table ----


def test_anthropic_worker_resolves_to_claude_adapter():
    prof = ExecutorProfile(role="worker", model_id="claude-opus-4-8")
    adapter = resolve_worker_adapter(prof, claude_options=object())
    assert isinstance(adapter, ClaudeWorkerAdapter)
    assert isinstance(adapter, WorkerAdapter)  # satisfies the port protocol


def test_non_claude_worker_is_refused_until_e4_gate():
    prof = ExecutorProfile(role="worker", model_id="mercury-2", provider="inception")
    with pytest.raises(ValueError, match="gated"):
        resolve_worker_adapter(prof, claude_options=object())


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
        )


async def test_run_one_turn_maps_turn_result_to_iteration_usage():
    session = _FakeSession()
    assert isinstance(session, WorkerSession)  # satisfies the port protocol
    state = State(task_id="t", goal="g", iteration=4)
    chunks, usage = await _run_one_turn(
        session=session, user_message="do the thing", state=state
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
