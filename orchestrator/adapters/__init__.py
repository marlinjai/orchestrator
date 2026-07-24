"""Executor adapters: concrete providers behind the ports in orchestrator/ports.py.

Selection is a small literal table keyed by (role, provider), NOT a plugin
registry (the spec's named #1 scope-creep risk). An unknown combination fails
loud at resolve time (startup), never at turn time.
"""

from __future__ import annotations

from orchestrator.executor import ExecutorProfile
from orchestrator.ports import WorkerAdapter


def resolve_worker_adapter(profile: ExecutorProfile, *, claude_options) -> WorkerAdapter:
    """Resolve the worker adapter for an executor profile.

    Until the E4 gate (held-out verifier + measured ``time_to_verified_ms`` win
    via best-of-N) is passed, the ONLY worker provider is Anthropic: a config
    that points the worker at a non-Claude provider is refused loudly here, at
    startup, before any Worker turn runs. ``claude_options`` is the
    ``ClaudeAgentOptions`` built by ``build_worker_options`` (typed loosely to
    keep this module SDK-import-free until an adapter needs it).
    """
    if profile.provider == "anthropic":
        from orchestrator.adapters.claude_worker import ClaudeWorkerAdapter

        return ClaudeWorkerAdapter(claude_options)
    raise ValueError(
        f"no worker adapter for provider {profile.provider!r} (model "
        f"{profile.model_id!r}): non-Claude code-writing is gated behind the "
        "E4 best-of-N + held-out-verifier experiment "
        "(docs/plans/2026-07-24-hexagonal-executor-ports.md)"
    )
