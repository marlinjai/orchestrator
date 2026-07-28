---
title: Hexagonal executor ports (ports-and-adapters seam for exchangeable models)
status: decided (E1+E2 implemented 2026-07-24; E3+E4 open)
date: 2026-07-24
revised: 2026-07-24 (v2 after reading the Inception Labs docs + OpenAPI spec)
owner: marlin
supersedes: none
related:
  - goals/orchestrator-executor-profile-mercury-recon.md
  - docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md
  - ROADMAP.md (Wave 2 per-role executor seam)
---

# Hexagonal Executor Ports (v2)

Make the orchestrator's execution layer a true ports-and-adapters (hexagonal) architecture: every role (worker, recon, planner) talks to a **port** (a small Python Protocol), and the concrete model/provider lives in an **adapter** behind it. Swapping Claude for Mercury 2 becomes a config + adapter change, never a control-loop change.

## What changed in v2

v1 assumed Mercury was a raw completion endpoint, which would have forced us to rebuild the whole agentic loop and argued for drawing the port at the model-call level. The Inception Labs OpenAPI spec disproves that assumption: **`mercury-2` chat completions support native tool calling** (`tools` + `tool_choice: auto|required|none`, OpenAI-compatible shape), structured outputs via `response_format`, `reasoning_effort` (`instant|low|medium|high`), streaming, 128K context. Mercury already runs inside third-party agentic coding harnesses (OpenCode, Roo Code, Kilo Code, Cursor). Measured ~1,000 output tokens/sec at $0.25/M input, $0.75/M output; time-to-first-token ~4s; Artificial Analysis Intelligence Index 21 (well below Opus-class).

Consequences:
1. The port stays at the **whole-turn** level. A Mercury worker adapter is a conventional OpenAI-style tool loop (~200-400 lines), not an SDK rebuild.
2. The Mercury-as-coder experiment is cheap enough that best-of-N Mercury attempts cost near-nothing next to metered Opus. The intelligence gap (index 21) is exactly what the experiment measures: hypothesis is that with Opus planning + recon, execution is mechanical enough for a fast cheap model to win on time-to-verified-result.

## Where we already are

| Piece | Status | Location |
|---|---|---|
| Role -> model routing port | DONE (`ExecutorProfile`, `resolve_executor(role)`) | `orchestrator/executor.py:106-210` |
| Foreign-provider transport | DONE, recon-only (`MercuryTransport`, secrets-proxy `/raw` forward, server-side key) | `executor.py:250-315` |
| Recon adapter (Mercury) | DONE but dormant (`run_recon` never called from the loop) | `orchestrator.py:~312-366` |
| Worker port | MISSING: Worker hard-wired to the Claude Agent SDK | `worker.py:302-384+` |
| Telemetry | recon-only (`ReconRecord` on `state.last_recon`) | `state.py:89-99` |

## Invariants (unchanged, load-bearing)

1. **Judge invariant**: both Proxies stay Claude. `ExecutorProfile.is_claude` keeps enforcing it.
2. **Operator-config-only routing**: `[executors.<role>]` in `~/.config/orchestrator/config.toml`. Never goal frontmatter, never repo registry.
3. **No plugin registry**: adapters are a small literal dict. One generic OpenAI-compatible adapter covers Mercury and future compatible providers without adapter-per-vendor creep.
4. **Key hygiene**: foreign keys only ever server-side via the secrets proxy `/raw` endpoint; `apply_env_contract` scrub stays first in every spawn path. The orchestrator process never holds the Inception key.
5. **Fail loud**: adapter unavailable -> warning + Claude fallback (recon) or hard error (worker), never silent skip.
6. **Non-Claude code-writing stays gated**: a Mercury worker only goes live behind best-of-N with a held-out verifier and a measured `time_to_verified_ms` win. This plan builds the port and the experiment rig; the default stays Claude until the data says otherwise.

## Ports (the interface layer)

New `orchestrator/ports.py` (leaf module, no SDK import), as `typing.Protocol`s:

```python
class WorkerPort(Protocol):
    """One agentic coding turn against a workspace (whole-turn boundary)."""
    def run_turn(self, cfg: TurnConfig, profile: ExecutorProfile) -> TurnResult: ...

class ReconPort(Protocol):
    def run(self, question: str, profile: ExecutorProfile) -> ReconFindings: ...
```

`TurnConfig` / `TurnResult` are extracted from the current `run_worker_turn` signature. Provider-specific knobs (MCP servers for Claude, `reasoning_effort` for Mercury) live on the profile/adapter side, not in `TurnConfig`, so the contract stays provider-neutral.

### ExecutorProfile extensions

- `provider: Literal["anthropic", "inception"]` as an **explicit field** (TOML `provider = "..."`), validated at load. No inference from model-ID string patterns.
- `reasoning_effort: str | None` (Inception-only knob; `high` for hard steps, `low`/`instant` for mechanical ones). Rejected for `provider = "anthropic"` at load time.
- `cost_ceiling_usd`: either enforced against usage telemetry in E3 or deleted. No dead safety-looking config.

## Adapters

- `adapters/claude_worker.py`: wraps today's `build_worker_options` + `run_worker_turn` (Claude Agent SDK, hooks isolation, MCP ceiling, env contract). Byte-for-byte default behavior.
- `adapters/openai_compat_worker.py`: generic tool loop over an OpenAI-compatible chat-completions endpoint, routed through the secrets-proxy `/raw` transport. Tools: read file, edit file, run command, all confined to the attempt worktree; same verify gate as Claude. Works for `mercury-2` and any future compatible provider.
- `adapters/claude_recon.py` / `adapters/mercury_recon.py`: today's `_claude_recon` and `run_mercury_recon`, repackaged.
- Selection: `resolve_adapter(profile)` keyed on `(role, provider)`. Unknown combo = `ValueError` at startup, not turn time.

## Phases

**E1: wire the dormant recon seam, config-gated.** Call `orchestrator.run_recon` from `run_orchestrator` **only when an `[executors.recon]` override exists** (or explicit `recon = true`), so default runs add zero extra model calls. Record `ReconRecord`. Small, ships alone.

**E2: extract WorkerPort + `provider` field.** Move `TurnConfig`/`TurnResult` out of `worker.py`, wrap the SDK path as `ClaudeWorkerAdapter`, add `provider`/`reasoning_effort` to `ExecutorProfile`, route the loop through `resolve_adapter`. Golden test: same goal, seam off vs on, terminal `state.json` identical minus timestamps.

**E3: unify telemetry + enforce cost ceiling + latency decomposition.** Generalize `ReconRecord` to per-role `ExecutorRecord` (executor, provider, model_id, elapsed_ms, ok, ran_at) appended per turn. Wire `cost_ceiling_usd` to usage accounting or delete it. Logged, never gated (except the ceiling, which aborts loudly).

Each `ExecutorRecord` additionally carries a per-model-call latency decomposition, because an agentic turn is many short generations, not one long one, and each call pays time-to-first-token (TTFT):

```
calls: list[CallLatency]
  ttft_ms          # request sent -> first token
  generation_ms    # first token -> last token
  tool_ms          # tool execution between this call and the next
  output_tokens
```

Aggregates (`total_ttft_ms`, `total_generation_ms`, `total_tool_ms`, `call_count`) roll up onto the record so `time_to_verified_ms` can be decomposed into waiting vs generating vs tooling without reading per-call rows. The Claude SDK adapter fills what its stream exposes (best effort, `None` for unavailable fields); the OpenAI-compat adapter measures all three directly since it owns the HTTP calls.

**E4: OpenAI-compatible worker adapter + the Mercury experiment.** Build `openai_compat_worker`, then race Claude vs Mercury on the same goals via the existing `--best-of` machinery with the held-out verifier, selection and comparison on `time_to_verified_ms`. Mercury becomes an allowed worker default only on a measured win. Needs its own goal file.

TTFT is a first-class experiment dimension. Mercury's headline ~1,000 tok/s comes with ~4s TTFT at default `reasoning_effort: medium`; in a tool loop of 30-60 short calls per turn, TTFT can dominate wall-clock and erase the throughput win. The Mercury cohort therefore runs with per-step effort tuning (`instant`/`low` for mechanical steps, `high` where the plan flags a hard step; also evaluate the API's `realtime` flag), and the E3 decomposition tells us whether time is lost waiting, generating, or tooling. Decision rule: if `total_ttft_ms` dominates the Mercury cohort and Inception's own knobs cannot close it, that is the trigger to consider a low-TTFT alternative model, added as one more `(role, provider)` adapter entry, never an architecture change.

## Non-goals

- No plugin/registry system, no dynamic adapter discovery.
- No planner adapter work yet (planner stays Claude; the port covers it later for free).
- No change to Marlin Proxy / Decision Proxy (judge invariant).
- `mercury-edit-2` (FIM/edit endpoints, no tool calling) is out of scope; if ever used it would be a tool *inside* a worker, not an executor.

## Reality update (2026-07-24)

E1 + E2 implemented and shipped on PR #14 (branch `plan/hexagonal-executor-ports`): `ports.py`, `adapters/claude_worker.py`, explicit `provider` + `reasoning_effort` on `ExecutorProfile`, config-gated recon wiring. 461 tests green, ruff clean. SKILL.md + ROADMAP updated in the same PR. E3 and E4 remain open.

Downstream consumers of this seam (recorded here because the knowledge-base backlog is not available on hermes): the autonomous-orchestration skill on the MacBook (picks everything up via git pull; needs its own `~/.config/orchestrator/config.toml` entries and Tailscale reach to the secrets proxy), and the Lumitra Agentic OS Platform (`~/workspace/lumitra/agentic-os-platform`), whose open milestone **M9 "Mercury sprint worker" IS this plan's E4** (design doc `docs/plans/2026-07-17-agentic-os-saas-design.md`, M9 row). M9 is therefore blocked on: (1) PR #14 review + merge, (2) E3 telemetry, (3) E4 adapter + experiment, (4) the INCEPTION_API_KEY scaffold in Infisical `/providers` (placeholder flow).

## Next steps (ordered, as of 2026-07-24)

1. **Marlin: review + merge PR #14** (`plan/hexagonal-executor-ports`). Everything below waits on it. Contents: this plan + E1/E2, 461 tests green, default behavior unchanged. NOTE: until this merges, this plan file exists only on the branch, not in the main checkout.
2. **E3: latency telemetry** (small slice, can run autonomously). Per-call `CallLatency` on a generalized `ExecutorRecord`, plus enforce-or-delete `cost_ceiling_usd`. No experiment is interpretable without it.
3. **Operator prerequisite: scaffold `INCEPTION_API_KEY`** in Infisical (`/providers`, project id in `executor.INCEPTION_PROJECT_ID`) via the placeholder flow (Claude sets `PLACEHOLDER_REPLACE_ME`, Marlin fills the real value in the UI). Then a live E1 smoke: `[executors.recon] model_id = "mercury-2", provider = "inception"` on a dogfood goal, asserting `state.last_recon.executor == "mercury"` and Claude fallback when the proxy is down.
4. **E4: the experiment** (large slice, needs its own goal file). `adapters/openai_compat_worker.py`, then Claude vs Mercury via `--best-of` with a held-out verifier, decided on `time_to_verified_ms` with the TTFT decomposition from E3. Exit criterion in Verification below.
5. **Platform side, after E4**: wire M9's sprint-worker respawn (handover doc for the 128K window) in `~/workspace/lumitra/agentic-os-platform`. That repo's other open items are out of this plan's scope: the AgentOS/Paperclip sunset decision (needs Marlin's explicit go) and the Uptime Kuma monitors.
6. **MacBook**: after merge, `git pull` the orchestrator checkout there; add `[executors.*]` entries to its own `~/.config/orchestrator/config.toml` to enable Mercury recon from the Mac (the secrets proxy is already reachable over Tailscale).

## Verification

- Existing suite green after E2 with no operator config; golden `state.json` invariance test.
- New tests: adapter resolution table, fake WorkerPort turn, judge-invariant regression (non-Claude worker without held-out gate -> refuse), profile validation (`provider` required for non-Claude, `reasoning_effort` rejected for Anthropic).
- E1 smoke: run with `[executors.recon] model_id = "mercury-2"` shows `state.last_recon.executor == "mercury"`, and Claude fallback on proxy-down.
- E4 exit criterion: N >= 10 goals, Mercury cohort median `time_to_verified_ms` < Claude cohort, held-out green rate within an agreed band.
