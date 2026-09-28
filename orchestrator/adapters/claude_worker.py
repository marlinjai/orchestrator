"""Claude worker adapter: the Claude Agent SDK session behind the WorkerPort.

Wraps the existing, proven machinery (``build_worker_options`` hook isolation,
MCP ceiling, env contract, ``run_worker_turn`` streaming) in the provider-neutral
``WorkerAdapter``/``WorkerSession`` shape. The options arrive fully built, so
every Worker safety rail (hook isolation, the worktree path guard, the MCP
ceiling) applies exactly as it did before the port existed.

Two stream facts shape the accounting here, both verified against real Claude
Code transcripts:

- The CLI emits one ``AssistantMessage`` PER CONTENT BLOCK (thinking, text,
  tool_use), and every block of a model call repeats that call's full
  ``usage``. Token usage is therefore deduplicated by ``message_id``; summing it
  per message counted each call once per block.
- The turn-closing ``ResultMessage`` also carries a ``usage`` total. It is NOT
  added on top of the per-call usage (that counted the turn twice). It is used
  instead of the per-call figures whenever any model call in the turn carried no
  usage (the SDK types assistant usage as nullable), so a missing call can never
  make the token caps and the cost estimate silently under-count. The two
  sources are never mixed: per-call usage when every call reported it, else the
  result total, else the partial per-call figures as the best available.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    ToolUseBlock,
    UserMessage,
)

from orchestrator.ports import OnText, TurnResult
from orchestrator.state import CallLatency
from orchestrator.transcript import extract_model, extract_text
from orchestrator.worker import run_worker_turn

Clock = Callable[[], float]


def _ms(seconds: float) -> int:
    return max(0, int(seconds * 1000))


class _CallTracker:
    """Splits a turn's message stream into top-level model calls.

    ``input_at`` is when the model last received input (the query, then each
    tool result). A new top-level ``message_id`` opens a call whose
    ``response_ms`` runs from ``input_at`` to that call's last block. When a
    call ended in tool use, the gap from its last block to the next input is
    its ``tool_ms``. Sub-agent messages (``parent_tool_use_id`` set) happen
    inside a tool call, so they count toward the parent's ``tool_ms`` rather
    than opening calls of their own.
    """

    def __init__(self, started_at: float) -> None:
        self.calls: list[CallLatency] = []
        self._input_at = started_at
        self._current_id: str | None = None
        self._call_start = started_at
        self._last_block_at = started_at
        self._uses_tool = False
        self._anon = 0

    def _close_tool_gap(self) -> None:
        if self.calls and self._uses_tool and self._input_at > self._last_block_at:
            self.calls[-1].tool_ms = _ms(self._input_at - self._last_block_at)

    def on_assistant(self, msg: AssistantMessage, now: float) -> None:
        if msg.parent_tool_use_id is not None:
            return
        msg_id = msg.message_id
        if msg_id is None:
            self._anon += 1
            msg_id = f"_anonymous-{self._anon}"
        if msg_id != self._current_id:
            self._close_tool_gap()
            self._current_id = msg_id
            self._call_start = self._input_at
            self._uses_tool = False
            self.calls.append(CallLatency())
        call = self.calls[-1]
        self._last_block_at = now
        call.response_ms = _ms(now - self._call_start)
        if any(isinstance(b, ToolUseBlock) for b in msg.content):
            self._uses_tool = True
        out = (msg.usage or {}).get("output_tokens")
        if isinstance(out, int):
            call.output_tokens = out

    def on_user(self, msg: UserMessage, now: float) -> None:
        if msg.parent_tool_use_id is None:
            self._input_at = now

    def finish(self) -> list[CallLatency]:
        self._close_tool_gap()
        return self.calls


class ClaudeWorkerSession:
    """One live Claude SDK conversation, spanning many turns."""

    def __init__(self, client: ClaudeSDKClient, *, clock: Clock = time.monotonic) -> None:
        self._client = client
        self._clock = clock

    async def run_turn(self, user_message: str, *, on_text: OnText | None = None) -> TurnResult:
        result = TurnResult()
        tracker = _CallTracker(self._clock())
        # Last usage seen per model call (every content block repeats it), and
        # every call seen at all, so a call that never reported usage is known.
        usage_by_call: dict[str, dict] = {}
        calls_seen: set[str] = set()
        anonymous = 0
        result_usage: dict | None = None
        async for msg in run_worker_turn(client=self._client, user_message=user_message):
            now = self._clock()
            text = extract_text(msg)
            if text:
                result.chunks.append(text)
                if on_text is not None:
                    on_text(text)
            if isinstance(msg, AssistantMessage):
                tracker.on_assistant(msg, now)
                key = msg.message_id
                if key is None:
                    anonymous += 1
                    key = f"_anonymous-{anonymous}"
                calls_seen.add(key)
                if isinstance(msg.usage, dict):
                    usage_by_call[key] = msg.usage
            elif isinstance(msg, UserMessage):
                tracker.on_user(msg, now)
            elif isinstance(msg, ResultMessage):
                result.is_error = bool(msg.is_error)
                result.error_subtype = msg.subtype if msg.is_error else None
                if isinstance(msg.usage, dict):
                    result_usage = msg.usage
            if not result.model:
                m = extract_model(msg)
                if m:
                    result.model = m
        usages = list(usage_by_call.values())
        complete = calls_seen <= usage_by_call.keys()
        if not complete and result_usage is not None:
            usages = [result_usage]
        for u in usages:
            result.input_tokens += int(u.get("input_tokens", 0) or 0)
            result.output_tokens += int(u.get("output_tokens", 0) or 0)
            result.cache_read_tokens += int(u.get("cache_read_input_tokens", 0) or 0)
            result.cache_creation_tokens += int(u.get("cache_creation_input_tokens", 0) or 0)
        result.calls = tracker.finish()
        return result


class ClaudeWorkerAdapter:
    """WorkerAdapter for the Anthropic provider (the default and, until the E4
    gate is passed, the only worker adapter)."""

    def __init__(self, options: ClaudeAgentOptions) -> None:
        self._options = options

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ClaudeWorkerSession]:
        async with ClaudeSDKClient(options=self._options) as client:
            yield ClaudeWorkerSession(client)
