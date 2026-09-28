"""E3 of the hexagonal executor ports plan: per-role executor telemetry.

Covers:
- ``ExecutorRecord.build`` rollups (sum only measured fields, ``None`` when no
  call measured one, never a fabricated zero);
- the Claude adapter's per-call decomposition over a scripted SDK stream with a
  fake clock: one call per ``message_id`` even though the CLI emits one
  ``AssistantMessage`` per content block, ``response_ms`` from the last input,
  ``tool_ms`` across a tool round trip, sub-agent messages folded into the
  parent's tool time;
- the token-usage fix: usage deduplicated per ``message_id`` and the
  ``ResultMessage`` total no longer added on top;
- recon telemetry: appended to ``executor_records`` and pointed at by
  ``last_recon``, one call row for a Mercury round trip, none for Claude;
- the loop persists one worker record per turn across the post-turn reload.
"""

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from orchestrator.adapters.claude_worker import ClaudeWorkerSession
from orchestrator.executor import ReconFindings, record_recon
from orchestrator.state import CallLatency, ExecutorRecord, State


# ---- rollups ----


def test_rollups_sum_only_measured_fields():
    rec = ExecutorRecord.build(
        role="worker",
        executor="claude",
        provider="anthropic",
        model_id="m",
        elapsed_ms=500,
        calls=[
            CallLatency(response_ms=100, tool_ms=30),
            CallLatency(response_ms=200),
        ],
    )
    assert rec.call_count == 2
    assert rec.total_response_ms == 300
    assert rec.total_tool_ms == 30
    # Nothing measured TTFT or generation: the rollup says "unknown", not 0.
    assert rec.total_ttft_ms is None
    assert rec.total_generation_ms is None


def test_rollups_of_no_calls_are_unknown():
    rec = ExecutorRecord.build(
        role="recon", executor="claude", provider="anthropic", model_id="m", elapsed_ms=9
    )
    assert rec.call_count == 0
    assert rec.calls == []
    assert rec.total_response_ms is None
    assert rec.total_tool_ms is None


# ---- Claude adapter over a scripted SDK stream ----


class _FakeClient:
    """Stands in for ClaudeSDKClient: ``run_worker_turn`` calls ``query`` then
    iterates ``receive_response``."""

    def __init__(self, messages):
        self._messages = messages
        self.queries: list[str] = []

    async def query(self, message: str) -> None:
        self.queries.append(message)

    async def receive_response(self):
        for m in self._messages:
            yield m


class _Clock:
    """Returns scripted monotonic times (seconds), one per read."""

    def __init__(self, times):
        self._times = list(times)

    def __call__(self) -> float:
        return self._times.pop(0)


def _assistant(msg_id, blocks, *, out, inp=100, parent=None):
    return AssistantMessage(
        content=blocks,
        model="claude-opus-4-8",
        parent_tool_use_id=parent,
        usage={
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 1,
        },
        message_id=msg_id,
    )


def _tool_result(parent=None):
    return UserMessage(
        content=[ToolResultBlock(tool_use_id="tu1", content="ok")], parent_tool_use_id=parent
    )


def _result(total_in, total_out):
    return ResultMessage(
        subtype="success",
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        num_turns=2,
        session_id="s",
        usage={"input_tokens": total_in, "output_tokens": total_out},
    )


async def test_claude_adapter_decomposes_calls_and_dedupes_usage():
    # Call A: three blocks (thinking, text, tool_use) sharing message id "a",
    # each repeating A's usage. Then a sub-agent message and the tool result.
    # Call B: two blocks sharing id "b". Then the turn's ResultMessage.
    messages = [
        _assistant("a", [ThinkingBlock(thinking="hm", signature="s")], out=50),
        _assistant("a", [TextBlock(text="reading ")], out=50),
        _assistant("a", [ToolUseBlock(id="tu1", name="Read", input={})], out=50),
        _assistant("sub", [TextBlock(text="")], out=999, inp=5, parent="tu1"),
        _tool_result(),
        _assistant("b", [ThinkingBlock(thinking="ok", signature="s")], out=20),
        _assistant("b", [TextBlock(text="done")], out=20),
        _result(total_in=9_999, total_out=9_999),
    ]
    # One clock read at turn start, then one per streamed message.
    clock = _Clock([0.0, 1.0, 1.5, 2.0, 2.4, 3.0, 4.0, 4.2, 4.3])
    client = _FakeClient(messages)
    seen: list[str] = []

    result = await ClaudeWorkerSession(client, clock=clock).run_turn(
        "go", on_text=seen.append
    )

    assert client.queries == ["go"]
    assert result.chunks == ["reading ", "done"]
    assert seen == ["reading ", "done"]
    assert result.model == "claude-opus-4-8"

    # Two top-level calls, not seven messages; the sub-agent does not open one.
    assert len(result.calls) == 2
    a, b = result.calls
    assert a.response_ms == 2000  # query at 0.0 -> A's last block at 2.0
    assert a.tool_ms == 1000  # A's last block at 2.0 -> tool result at 3.0
    assert a.output_tokens == 50
    assert b.response_ms == 1200  # tool result at 3.0 -> B's last block at 4.2
    assert b.tool_ms is None  # B ended the turn without tool use
    assert b.output_tokens == 20
    # The Claude SDK does not stream tokens here, so no TTFT split is claimed.
    assert a.ttft_ms is None and a.generation_ms is None

    # Usage: each call counted once (A=50, B=20, sub-agent=999 out; three
    # inputs), and the ResultMessage total NOT added on top.
    assert result.output_tokens == 50 + 20 + 999
    assert result.input_tokens == 100 + 100 + 5
    assert result.cache_read_tokens == 30
    assert result.cache_creation_tokens == 3


async def test_claude_adapter_falls_back_to_result_usage_when_calls_carry_none():
    # A CLI that stopped emitting per-call usage must not make the token caps
    # read zero: the ResultMessage total is then the turn's usage.
    bare = AssistantMessage(
        content=[TextBlock(text="hi")], model="claude-opus-4-8", usage=None, message_id="a"
    )
    client = _FakeClient([bare, _result(total_in=300, total_out=40)])
    result = await ClaudeWorkerSession(client, clock=_Clock([0.0, 1.0, 1.1])).run_turn("go")
    assert result.input_tokens == 300
    assert result.output_tokens == 40
    assert len(result.calls) == 1
    assert result.calls[0].output_tokens is None


async def test_claude_adapter_turn_without_messages_has_no_calls():
    client = _FakeClient([])
    result = await ClaudeWorkerSession(client, clock=_Clock([0.0])).run_turn("go")
    assert result.calls == []
    assert result.output_tokens == 0


# ---- recon telemetry ----


def _findings(executor: str, model_id: str, elapsed_ms: int, ok: bool = True):
    return ReconFindings(
        question="q", findings="f", executor=executor, model_id=model_id,
        elapsed_ms=elapsed_ms, ok=ok,
    )


def test_mercury_recon_record_has_one_round_trip_call():
    state = State(task_id="t", goal="g", iteration=0)
    record_recon(state, _findings("mercury", "mercury-2", 1234))
    rec = state.last_recon
    assert rec is not None
    assert state.executor_records == [rec]
    assert rec.role == "recon"
    assert rec.executor == "mercury"
    assert rec.provider == "inception"
    assert rec.call_count == 1
    assert rec.total_response_ms == 1234


def test_claude_recon_record_claims_no_call_rows():
    state = State(task_id="t", goal="g")
    record_recon(state, _findings("claude", "claude-opus-4-8", 800, ok=False))
    rec = state.last_recon
    assert rec.provider == "anthropic"
    assert rec.ok is False
    assert rec.calls == []
    assert rec.total_response_ms is None


def test_executor_records_round_trip_through_state_json(tmp_path):
    from orchestrator.state import load_state, save_state

    state = State(task_id="t", goal="g")
    record_recon(state, _findings("mercury", "mercury-2", 10))
    path = tmp_path / "state.json"
    save_state(path, state)
    loaded = load_state(path)
    assert loaded.executor_records == state.executor_records
    assert loaded.last_recon == state.last_recon
