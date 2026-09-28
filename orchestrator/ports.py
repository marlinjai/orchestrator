"""Hexagonal executor ports: the provider-neutral interfaces the control loop
speaks to, with the concrete model/provider hidden behind adapters.

This is the E2 slice of docs/plans/2026-07-24-hexagonal-executor-ports.md. The
port is drawn at the WHOLE-TURN boundary: "run one agentic turn against a
workspace and return what happened." Provider-specific machinery (the Claude
Agent SDK session, or an OpenAI-compatible tool loop in a later wave) lives in
``orchestrator/adapters/``; the control loop never imports a provider SDK
through this module.

Leaf module: no SDK import, no adapter import. ``TurnResult`` is deliberately
provider-neutral; anything Claude-specific (MCP servers, hook isolation) or
Inception-specific (reasoning_effort) is configured on the adapter, never
threaded through the port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncContextManager, Callable, Protocol, runtime_checkable


# Called with each streamed text fragment as it arrives, so the control loop
# can print live progress without the port leaking provider message shapes.
OnText = Callable[[str], None]


@dataclass
class TurnResult:
    """What one worker turn produced, in provider-neutral terms.

    ``chunks`` are the assistant's streamed text fragments in order (the
    transcript window the Decision Proxy judges on). Token fields mirror
    ``IterationUsage``; an adapter fills what its provider exposes and leaves
    the rest at 0/None (best effort, never fabricated).
    """

    chunks: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    model: str | None = None


@runtime_checkable
class WorkerSession(Protocol):
    """A live worker conversation. One session spans many turns (the control
    loop iterates turns against the same session so the worker keeps context);
    the adapter owns whatever connection/process backs it."""

    async def run_turn(self, user_message: str, *, on_text: OnText | None = None) -> TurnResult:
        ...


@runtime_checkable
class WorkerAdapter(Protocol):
    """Factory for worker sessions. ``open()`` returns an async context manager
    so the adapter can guarantee teardown of its provider resources (SDK client,
    HTTP session) regardless of how the control loop exits."""

    def open(self) -> AsyncContextManager[WorkerSession]:
        ...
