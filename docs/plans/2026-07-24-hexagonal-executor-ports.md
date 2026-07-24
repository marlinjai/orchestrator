---
title: Hexagonal executor ports (ports-and-adapters seam for exchangeable models)
status: draft
date: 2026-07-24
owner: marlin
supersedes: none
related:
  - goals/orchestrator-executor-profile-mercury-recon.md
  - docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md
  - ROADMAP.md (Wave 2 per-role executor seam)
---

# Hexagonal Executor Ports

Make the orchestrator's execution layer a true ports-and-adapters (hexagonal) architecture: every role (worker, recon, planner) talks to a **port** (a small Python Protocol), and the concrete model/provider lives in an **adapter** behind it. Swapping Claude for Mercury (or anything else) becomes a config + adapter change, never a control-loop change.

## Where we already are

The Wave 2 seam (shipped dormant 2026-06-20) is already half of this:

| Piece | Status | Location |
|---|---|---|
| Role -> model routing port | DONE (`ExecutorProfile`, `resolve_executor(role)`) | `orchestrator/executor.py:106-210` |
| Foreign-provider transport port | DONE, recon-only (`MercuryTransport = Callable[[str, str, dict], str]`, `/raw` proxy forward, server-side key) | `executor.py:250-315` |
| Recon adapter (Mercury) | DONE but dormant (`run_recon` never called from the loop) | `orchestrator.py:~312-366` |
| Worker port | **MISSING**: Worker is hard-wired to the Claude Agent SDK | `worker.py:302-384+` |
| Telemetry | recon-only (`ReconRecord` on `state.last_recon`) | `state.py:89-99` |

## Invariants (unchanged, load-bearing)

1. **Judge invariant**: both Proxies stay Claude. `ExecutorProfile.is_claude` keeps enforcing it; tests in `tests/test_executor.py` stay.
2. **Operator-config-only routing**: `[executors.<role>]` in `~/.config/orchestrator/config.toml`. Never goal frontmatter, never repo registry.
3. **No provider registry**: adapters are a small literal dict, not a plugin system. The spec named registry-creep the #1 scope risk; this plan keeps it that way.
4. **Key hygiene**: foreign keys only ever server-side via the secrets proxy `/raw` endpoint; `apply_env_contract` scrub stays first in every adapter spawn path.
5. **Fail loud**: adapter unavailable -> warning + Claude fallback (recon) or hard error (worker), never silent skip.
6. **Non-Claude code-writing stays gated**: a Mercury worker adapter only goes live behind best-of-N with a held-out verifier and a measured `time_to_verified_ms` win. This plan builds the port; it does not flip that switch.

## Ports (the interface layer)

All in a new `orchestrator/ports.py` (leaf module, no SDK import), as `typing.Protocol`s:

```python
class CompletionPort(Protocol):
    """Single-shot, tool-free completion. Generalizes MercuryTransport."""
    def complete(self, system: str, prompt: str, params: dict) -> str: ...

class ReconPort(Protocol):
    def run(self, question: str, profile: ExecutorProfile) -> ReconFindings: ...

class WorkerPort(Protocol):
    """One agentic coding turn against a workspace."""
    def run_turn(self, cfg: TurnConfig, profile: ExecutorProfile) -> TurnResult: ...
```

`TurnConfig` / `TurnResult` are extracted from the current `run_worker_turn` signature so the Claude adapter is a pure wrap (byte-for-byte behavior with default config).

## Adapters

- `adapters/claude_worker.py`: wraps today's `build_worker_options` + `run_worker_turn` (Claude Agent SDK, hooks isolation, MCP ceiling, env contract). The only worker adapter that exists after this plan.
- `adapters/claude_recon.py`: today's `_claude_recon` (SDK `query()`, no tools).
- `adapters/mercury_recon.py`: today's `run_mercury_recon` over the `/raw` proxy transport.
- Adapter selection: `resolve_adapter(profile) -> WorkerPort | ReconPort`, a literal `{("worker", "claude-*"): ClaudeWorkerAdapter, ...}` mapping. Unknown combo = `ValueError` at startup, not at turn time.

## Phases

**E1: wire the dormant recon seam.** Call `orchestrator.run_recon` from `run_orchestrator` at the recon point (recon-early per the 2026-06-18 handover), record `ReconRecord`. First live proof of the seam. Small, ships alone.

**E2: extract WorkerPort.** Move `TurnConfig`/`TurnResult` types out of `worker.py`, wrap the SDK path as `ClaudeWorkerAdapter`, route the control loop through `resolve_adapter(resolve_executor("worker"))`. Zero behavior change with no operator config; test = existing suite green plus an adapter-fake turn test.

**E3: unify telemetry.** Generalize `ReconRecord` to a per-role `ExecutorRecord` (executor, model_id, elapsed_ms, ok, ran_at) appended per turn; `time_to_verified_ms` unchanged. Logged, never gated.

**E4 (gated, NOT in this plan's implementation scope):** `adapters/mercury_worker.py` behind `--best-of` + held-out verifier, compared on `time_to_verified_ms`. Requires its own goal file and the measured win before default-on.

## Non-goals

- No plugin/registry system, no dynamic adapter discovery.
- No planner adapter work yet (planner stays Claude; the port covers it for free later).
- No change to Marlin Proxy / Decision Proxy (judge invariant).

## Verification

- Full existing test suite green after E2 with no operator config (default-path invariance).
- New tests: adapter resolution table, fake WorkerPort turn, judge-invariant regression (worker non-Claude without gate -> refuse).
- E1 smoke: one real orchestrator run with `[executors.recon] model_id = "mercury"` shows `state.last_recon.executor == "mercury"` and Claude fallback on proxy-down.
