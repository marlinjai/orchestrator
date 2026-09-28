---
type: plan
title: Hexagonal executor ports (ports-and-adapters seam for exchangeable models)
status: completed
date: 2026-07-24
revised: 2026-09-28 (revived after PR #14 closed unmerged; E1 to E4 shipped the same day, E4b verdict: Mercury wins)
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
| Foreign-provider transport | DONE, recon-only (`MercuryTransport`, secrets-proxy provider forward `/forward/inception/chat/completions`, server-side key; see the 2026-09-28 transport update) | `executor.py` `_proxy_provider_forward` |
| Recon adapter (Mercury) | DONE but dormant (`run_recon` never called from the loop) | `orchestrator.py:~312-366` |
| Worker port | MISSING: Worker hard-wired to the Claude Agent SDK | `worker.py:302-384+` |
| Telemetry | recon-only (`ReconRecord` on `state.last_recon`) | `state.py:89-99` |

## Invariants (unchanged, load-bearing)

1. **Judge invariant**: both Proxies stay Claude. `ExecutorProfile.is_claude` keeps enforcing it.
2. **Operator-config-only routing**: `[executors.<role>]` in `~/.config/orchestrator/config.toml`. Never goal frontmatter, never repo registry.
3. **No plugin registry**: adapters are a small literal dict. One generic OpenAI-compatible adapter covers Mercury and future compatible providers without adapter-per-vendor creep.
4. **Key hygiene**: foreign keys only ever server-side via the secrets proxy's provider forward (`/forward/<provider>/<op>`; originally specified as `/raw`, which the proxy refuses by design, see the 2026-09-28 transport update); `apply_env_contract` scrub stays first in every spawn path. The orchestrator process never holds the Inception key.
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
- `adapters/openai_compat_worker.py`: generic tool loop over an OpenAI-compatible chat-completions endpoint, routed through the secrets-proxy provider forward (streaming, so TTFT is measurable client-side). Tools: read file, edit file, run command, all confined to the attempt worktree; same verify gate as Claude. Works for `mercury-2` and any future compatible provider.
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

## Reality update (2026-09-28): revived

PR #14 closed unmerged on 2026-08-09, so none of the above reached main. On 2026-09-28 Marlin decided to revive the work rather than archive it: executor ports first, then M9 in the Agentic OS Platform. The six branch commits were rebased onto main (clean, no conflicts) and re-verified: 470 tests green, ruff clean. The seam carries main's later Worker changes unchanged, because `ClaudeWorkerAdapter` receives options already built by `build_worker_options`: the worktree path guard (the `can_use_tool` hard-deny on edits outside the attempt worktree) and the proxy-token-out-of-argv MCP config both apply exactly as before.

Correction to the M9 note above: M9 is a SUPERSET of E4, not the same thing. The Agentic OS side (`agentic-os-platform/docs/plans/2026-07-28-m9-executor-reconciliation.md`, Corrections 1 to 3) adds the sprint-worker respawn and its handover on top of the adapter.

## Reality update (2026-09-28): E3 shipped

- `CallLatency` + `ExecutorRecord` in `state.py`; `ReconRecord` is gone. `state.executor_records` gets one record per Worker turn (appended after the post-turn state reload, so handover turns count too) and per recon call; `state.last_recon` stays as the pointer the live E1 smoke asserts on. Rollups sum only measured fields and stay `None` otherwise.
- The TurnResult carries `calls`. The Claude adapter groups the stream by `message_id` and measures `response_ms` (last input to the call's last block) and `tool_ms` (last block to the next tool result); sub-agent messages fold into the parent's tool time. It does not claim a TTFT/generation split: the SDK only exposes that with partial-message streaming, which would change the message stream the loop sees. The OpenAI-compatible adapter (E4) owns its HTTP calls and fills all fields.
- Deviation from the E3 wording "per-role telemetry only": building the per-call tracker exposed a real accounting bug. The CLI emits one `AssistantMessage` per content block, each repeating the call's full usage, and the adapter also added the `ResultMessage` turn total on top, so recorded tokens (and with them the per-run token cap, the fleet daily cap and the cost estimate) were inflated by roughly the blocks-per-call count plus one. Usage is now deduplicated per `message_id`, and the result total is never added on top of it: it is used only as a fallback, replacing the per-call figures, when a model call in the turn carried no usage (the SDK types assistant usage as nullable), so the two sources are never mixed. Token figures in new runs are therefore lower than in older runs; they are now correct, not a regression.
- A turn the provider itself ends in error (`ResultMessage.is_error`) is carried on the `TurnResult` and recorded as a failed worker record (`ok=False`). The loop still continues to the Decision Proxy, which judges on git ground truth; the iteration, token and stagnation caps bound a Worker that keeps erroring. A `state.json` written before E3 (a `last_recon` without `role`/`provider`) is migrated on load into an `ExecutorRecord`, once.
- `cost_ceiling_usd` deleted, and rejected at load with a pointer to `--max-cost-usd` (a per-role ceiling needs per-role price attribution; the run-level cap already exists and is enforced).
- `orchestrator status` prints an `executor:<role>` line with the latency split; the test suite now isolates `ORCHESTRATOR_CONFIG_HOME` so a developer's real `[executors.recon]` can never make loop tests fire live recon calls.

## Reality update (2026-09-28): the Mercury transport was dead; replaced

The live recon smoke found the secrets proxy answering `/raw` with HTTP 501. `/raw` was never implemented, by design: a "run a shell command, return stdout unredacted" endpoint returns every injected secret for `printenv`. So every Mercury recon since the Wave 2 seam shipped silently fell back to Claude, which is why nothing looked broken. Consequences, all handled on 2026-09-28:

- **secrets-proxy#21** adds the replacement the proxy's own code had already named: a provider forward, `POST /forward/inception/chat/completions`. Literal route allowlist, the caller sends only the JSON body (steering fields rejected), the key is fetched server-side and only placed in the outbound header, caller headers dropped except `Accept`, no shell, response streamed back verbatim and flushed per chunk (so E4 can measure time-to-first-token), one audit line per call. Deploys on merge via its CI.
- **The key**: the orchestrator's `INCEPTION_PROJECT_ID` default was a synthetic UUID that pointed at nothing. The Agentic OS Platform project (`7c00cb5c-...`) already held a live `INCEPTION_API_KEY` at its root. It was copied server-side with `copy_secret` into a new `/providers` folder of that project (holding only provider keys, so the forward's fetch scope is one secret), fingerprint-matched and functionally checked (HTTP 200). Rotate both locations together. No human handled the value and no placeholder step was needed.
- **This repo**: `_proxy_raw_forward` and the curl builder are gone; `_proxy_provider_forward` POSTs the body to the route. `INCEPTION_PROJECT_ID` / `INCEPTION_SECRET_PATH` / `INCEPTION_SECRET_ENV` / `INCEPTION_ENDPOINT` are deleted (the proxy owns those coordinates now). The proxy token is resolved by the shared `proxy_token.resolve_proxy_token` (0600 file first), not only from the environment. `MERCURY_MODEL_ID` is `mercury-2` (Inception lists `mercury-2` and `mercury-2.5`; `mercury` does not exist).

## Next steps (ordered, as of 2026-09-28)

1. **DONE 2026-09-28. E1+E2** landed as #28 (this plan + the seam).
2. **DONE 2026-09-28. E3: latency telemetry** (own pull request). Per-call `CallLatency` on a generalized `ExecutorRecord`, plus enforce-or-delete `cost_ceiling_usd`. No experiment is interpretable without it.
3. **DONE 2026-09-28. E4a (the adapter and the gate) and E4b (the race, Mercury wins; see the verdict).** **E4: the OpenAI-compatible worker adapter** (own pull request). `adapters/openai_compat_worker.py`, the non-Claude worker gate (refuse without a held-out verifier), and the experiment rig: Claude vs Mercury via `--best-of` with a held-out verifier, decided on `time_to_verified_ms` with the TTFT decomposition from E3. Running the live cohort needs step 4. Exit criterion in Verification below.
4. **DONE 2026-09-28. Inception key + transport**: see the transport update above; no step for Marlin was needed. Live E1 smoke PASSED 2026-09-28 after secrets-proxy#21 deployed: the loop's `run_recon` with `[executors.recon] model_id = "mercury-2", provider = "inception", reasoning_effort = "low"` gave `state.last_recon.executor == "mercury"`, `ok`, one call, 2312 ms, a 695-character answer; with the proxy unreachable the transport raised `MercuryUnavailable`, the signal `run_recon` falls back to Claude on. The first Mercury completion this path has ever returned.
5. **Platform side, after E4**: M9's sprint worker in `agentic-os-platform`, per its reconciliation plan.
6. **MacBook**: after merge, pull the orchestrator checkout there and add `[executors.*]` entries to its own `~/.config/orchestrator/config.toml` to enable Mercury recon from the Mac (the secrets proxy is reachable over Tailscale).

## Reality update (2026-09-28): E4a shipped, E4b needs held-out test sets

E4 was split. **E4a (built)**: `orchestrator/adapters/openai_compat_worker.py`, a hand-rolled OpenAI-shaped tool loop over the provider forward with streaming. Tools `read_file` / `write_file` / `edit_file` / `list_dir` / `run_command` / `update_state` (the same schema constant and handler as the Claude Worker's MCP tool), confined through `worker.path_outside_root` (now the one check both adapters share), `run_command` under the denylist with a scrubbed env and a timeout, output capped, a 60-round per-turn cap that ends the turn visibly. The gate lives in `adapters.resolve_worker_adapter`: an `inception` worker is refused at startup without a held-out verifier. Provider errors carry an explicit `transient` flag that `retry.is_transient_sdk_error` now honors before its substring fallback (a terminal 400 whose body says "150233 tokens" contains "502" and would otherwise be retried). Measured per call: `ttft_ms`, `generation_ms`, `tool_ms`, `output_tokens`, and the new `server_ms` (Inception's `server_timing.server_latency_ms`), so network plus proxy overhead is `response_ms - server_ms`. Mercury pricing is in `MODEL_PRICING`.

Probe findings that shape the experiment (live, 2026-09-28): Mercury is a diffusion model and streams in a few large blocks, not token by token; a tool call arrives whole in the first chunk. So `generation_ms` is near zero and `ttft_ms` is effectively the whole model time per call; the TTFT-vs-throughput question in E4 reduces to "per-call latency times call count". Inception honors `stream_options.include_usage`.

Deliberately not built yet: per-step `reasoning_effort` tuning (apply the profile value uniformly until the E3 numbers show TTFT dominating). Open design question for the race, not blocking E4a: the loop's handover trigger reads `usage[-1].input_tokens`, which for both adapters is the turn's summed uncached prompt tokens, not the peak context size; with Mercury's 128K window and no prompt caching the summed figure can trigger handovers earlier than the real context requires. Measure on the first cohort before changing the trigger for both providers.

**Live E4a smoke, passed 2026-09-28**: `orchestrator start` with `[executors.worker] model_id = "mercury-2", provider = "inception"` and `--held-out` on a throwaway repo (goal: add `multiply` plus a test and commit). One iteration; the Claude Decision Proxy stopped; in-tree verify PASS; held-out PASS; `completed`. Worker record: 16 model calls, 13,332 ms worker time, of which TTFT 12,679 ms (Inception server time 8,017 ms, so roughly 290 ms of network plus proxy overhead per call), generation 50 ms, tools 454 ms; 23,808 input and 1,301 output tokens, about $0.01. The shape confirms the TTFT finding above: per-call latency times call count is the whole cost, and proxy transit is a measurable third of it.

**E4b (done, verdict below)**: the race itself. Setup decided by Marlin on 2026-09-28 (decision page `~/software-dev/decision-pages/2026-09-28-mercury-race.html`, all four recommendations taken):

1. **Goals**: a benchmark, not real backlog tasks: `bench/mercury-race/`, the `textkit` seed project and 10 self-contained goals (features, bug fixes, a new module, a CLI, a data structure), each specified precisely enough that hidden tests judge the spec. Every hidden suite is proven fair by `scripts/mercury_race.py validate` (fails on the seed, passes on a reference solution). If Mercury wins here, a second round on real tasks precedes M9.
2. **Hidden tests**: installed into `~/.orchestrator/verifier-vault/mercury-race/`, outside every repo. Accepted weakness: a Worker's shell runs as the same OS user and could read them; the logged commands would show it. A separate OS user is required before any real-repo round.
3. **Band**: Mercury's hidden-test pass rate must be within 10 percentage points of Claude's.
4. **Spend**: 2 attempts per goal per cohort (`--best-of 2`), about 40 runs.

Scoring (`scripts/mercury_race.py`, unit-tested): per goal and cohort, the fastest held-out-green attempt's `time_to_verified_ms`; a goal with no green attempt counts as infinitely slow; the cohort median is over all goals. Mercury wins only with N >= 10, a lower median, and the pass rate inside the band.

## Verdict (2026-09-28): Mercury wins the E4b race

Run `~/.orchestrator/mercury-race/2026-09-28` (`scripts/mercury_race.py run`, 10 goals, best-of-2 per cohort, 3 runs in parallel), scored against the pre-registered exit criterion:

| Goal | Claude | Mercury |
|---|---|---|
| 01-word-count | pass 23.6s | pass 33.7s |
| 02-slugify-dashes | pass 24.8s | pass 13.9s |
| 03-truncate-width | pass 27.7s | pass 14.9s |
| 04-roman | pass 30.2s | pass 18.9s |
| 05-csv-quotes | pass 31.5s | pass 41.6s |
| 06-cli-count | pass 31.3s | pass 13.4s |
| 07-case-convert | pass 29.0s | pass 14.9s |
| 08-duration-units | pass 28.3s | pass 15.1s |
| 09-lru-cache | pass 29.3s | pass 14.6s |
| 10-wrap | pass 27.0s | pass 19.7s |

Both cohorts: 10/10 goals held-out green. Median time to a verified result: **Claude 28.6s, Mercury 15.0s**. Exit criterion (N >= 10, Mercury faster, pass rate within 10 points): **met, Mercury wins.**

What the aggregate hides, from the 40 individual attempts (so the verdict is read correctly):

- Per attempt, Mercury's median is 18.5s against Claude's 30.4s, and its Worker-only median 13.5s against 25.2s: typically about 1.6x faster. But the MEANS are equal (Mercury 33.8s, Claude 32.3s): Mercury has a tail. 17 of 20 Mercury attempts finished in one iteration (Claude 20 of 20); the rest drifted into multi-iteration loops, and 2 of 20 Mercury attempts failed the hidden tests (Claude 0 of 20). Best-of-2 absorbs that tail, which is why the cohort result is clean. Mercury as a single-attempt Worker would be faster on average only if the tail is fixed.
- The tail has one visible cause (seen live in the dry run): Mercury narrates progress instead of calling `update_state`, the Claude Decision Proxy keeps asking it to reconcile, and the stagnation guard eventually stops it; once it "reverted unrelated seed files" in response. A Mercury-specific prompt nudge toward `update_state` is the obvious first fix.
- Cost over all 20 attempts: Mercury about $0.31, Claude about $8.89 (notional on the subscription, real on metered credit): about 29x cheaper.
- Mercury's model time is almost all time-to-first-token (345s TTFT over 310 calls, 260s of it Inception server time, generation 3.3s in total), so its per-call latency times call count is its whole cost, as predicted.
- Integrity: no attempt's commits mention the vault or the reference solutions, and no solution file is byte-identical to a reference. Caveat for this run: the Mercury adapter did not yet record its tool calls, so a read-only peek could not be ruled out from logs; it now writes `worker-tools.jsonl` next to `state.json` (every tool call, commands verbatim, file contents by size).
- No context handover fired in any of the 40 runs, so the handover-trigger question above stays open and unmeasured at this goal size.

Consequences: the orchestrator's non-Claude Worker path is validated on a benchmark, behind the held-out gate, and stays opt-in (the default Worker is still Claude; an operator enables Mercury per config home). M9 in the Agentic OS Platform may proceed. As the decision page set out, a second round on real repositories (hidden tests owned by a separate OS user) comes before Mercury does real work; that and the prompt nudge are the dated follow-ups on the ROADMAP.

## Verification

- Existing suite green after E2 with no operator config; golden `state.json` invariance test.
- New tests: adapter resolution table, fake WorkerPort turn, judge-invariant regression (non-Claude worker without held-out gate -> refuse), profile validation (`provider` required for non-Claude, `reasoning_effort` rejected for Anthropic).
- E1 smoke: run with `[executors.recon] model_id = "mercury-2"` shows `state.last_recon.executor == "mercury"`, and Claude fallback on proxy-down.
- E4 exit criterion: N >= 10 goals, Mercury cohort median `time_to_verified_ms` < Claude cohort, held-out green rate within an agreed band.
