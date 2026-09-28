"""Claude worker adapter: the Claude Agent SDK session behind the WorkerPort.

Wraps the existing, proven machinery (``build_worker_options`` hook isolation,
MCP ceiling, env contract, ``run_worker_turn`` streaming) in the provider-neutral
``WorkerAdapter``/``WorkerSession`` shape. With the default (Claude) executor
profile this is byte-for-byte the pre-port behavior; the only change is where
the code lives.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from orchestrator.ports import OnText, TurnResult
from orchestrator.transcript import extract_model, extract_text, extract_usage
from orchestrator.worker import run_worker_turn


class ClaudeWorkerSession:
    """One live Claude SDK conversation, spanning many turns."""

    def __init__(self, client: ClaudeSDKClient) -> None:
        self._client = client

    async def run_turn(self, user_message: str, *, on_text: OnText | None = None) -> TurnResult:
        result = TurnResult()
        async for msg in run_worker_turn(client=self._client, user_message=user_message):
            text = extract_text(msg)
            if text:
                result.chunks.append(text)
                if on_text is not None:
                    on_text(text)
            u = extract_usage(msg)
            if u:
                result.input_tokens += int(u.get("input_tokens", 0) or 0)
                result.output_tokens += int(u.get("output_tokens", 0) or 0)
                result.cache_read_tokens += int(u.get("cache_read_input_tokens", 0) or 0)
                result.cache_creation_tokens += int(u.get("cache_creation_input_tokens", 0) or 0)
            if not result.model:
                m = extract_model(msg)
                if m:
                    result.model = m
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
