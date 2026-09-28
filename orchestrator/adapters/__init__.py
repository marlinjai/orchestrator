"""Executor adapters: concrete providers behind the ports in orchestrator/ports.py.

Selection is a small literal table keyed by (role, provider), NOT a plugin
registry (the spec's named #1 scope-creep risk). An unknown combination fails
loud at resolve time (startup), never at turn time.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.executor import CLAUDE_MODEL_ID, PROVIDER_FORWARD_ROUTES, ExecutorProfile
from orchestrator.ports import WorkerAdapter


def resolve_worker_adapter(
    profile: ExecutorProfile,
    *,
    claude_options,
    held_out_verify: str | None = None,
    work_dir: Path | None = None,
    state_path: Path | None = None,
    context_limit: int = 0,
) -> WorkerAdapter:
    """Resolve the worker adapter for an executor profile, at startup.

    - ``anthropic``: the Claude Agent SDK adapter. ``claude_options`` is the
      ``ClaudeAgentOptions`` built by ``build_worker_options`` (typed loosely to
      keep this module SDK-import-free). A non-default Anthropic ``model_id`` is
      pinned onto the options; the default profile leaves them untouched
      (byte-for-byte pre-port).
    - a provider with a secrets-proxy forward route (``inception``): the
      OpenAI-compatible tool-loop adapter, behind the E4 GATE: non-Claude
      code-writing is allowed only when the run has a held-out verifier (the
      registry's ``held_out_verify`` or ``--held-out``), because the in-tree
      verify is Worker-reachable and a weaker model is exactly where a
      reward-hacked green would slip through. ``best-of-N`` already requires a
      held-out, so every experiment cohort passes this gate.
    - anything else: refused.

    Every refusal is a ``ValueError`` here, before any Worker turn runs.
    """
    if profile.provider == "anthropic":
        from orchestrator.adapters.claude_worker import ClaudeWorkerAdapter

        if profile.model_id != CLAUDE_MODEL_ID:
            claude_options = replace(claude_options, model=profile.model_id)
        return ClaudeWorkerAdapter(claude_options)
    if profile.provider in PROVIDER_FORWARD_ROUTES:
        if not held_out_verify:
            raise ValueError(
                f"worker provider {profile.provider!r} (model {profile.model_id!r}) "
                "needs a held-out verifier: non-Claude code-writing runs only when "
                "the repo registry sets held_out_verify or the run passes --held-out "
                "(docs/plans/2026-07-24-hexagonal-executor-ports.md, E4 gate)"
            )
        if work_dir is None or state_path is None:
            raise ValueError(
                f"worker provider {profile.provider!r} needs the run's work_dir and "
                "state_path to confine its tools and record state"
            )
        from orchestrator.adapters.openai_compat_worker import OpenAICompatWorkerAdapter

        return OpenAICompatWorkerAdapter(
            profile=profile, work_dir=work_dir, state_path=state_path, context_limit=context_limit
        )
    raise ValueError(
        f"no worker adapter for provider {profile.provider!r} (model {profile.model_id!r})"
    )
