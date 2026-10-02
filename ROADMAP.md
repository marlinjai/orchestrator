# ROADMAP

Living tracker for orchestrator work. Read top to bottom: shipped at the top, in-flight in the middle, queued at the bottom.

## Shipped

### Mercury transport: one proxy CLI process per Worker session (2026-10-02)
- **The per-call overhead is gone.** Since the secrets-proxy caller-identity switch every Mercury model call spawned the `secrets-proxy-call` Node CLI, which read the credentials and logged in to Infisical again. `ForwardSession` in `orchestrator/adapters/openai_compat_worker.py` now keeps ONE `secrets-proxy-call forward-session` process per Worker session (secrets-proxy#27): one JSON request line in, id-tagged frames out, the token never leaves the CLI. The process starts on first use, is killed and restarted after a stalled stream, and ends with the session.
- **Measured** (benchmark remeasure, Mercury cohort, 20 attempts, `~/.orchestrator/mercury-race/2026-10-02-forward-session`): transport overhead per call (response time minus the provider's own server time) median 259ms, against 662ms with a CLI per call (`2026-09-28-tail-fix-final`) and 295ms on the original shared-token transport (`2026-09-28`). Median time to first token 592ms against 998ms. Per attempt: 20 of 20 hidden-test green, 20 of 20 in one iteration, median 15.7s (was 21.2s), mean 23.4s (was 29.2s). Two calls of 298 stalled at the provider and recovered through the 60s timeout and in-place retry.
- Needs the secrets-proxy CLI at 0.5.0 or newer; an older build fails the run loud and says how to rebuild.

### Mercury handover turn: the token watcher seen live, and the handover it triggers fixed (2026-10-02)
- **Seen live for the first time.** The token watcher (#35, handover at `min(context_handover_tokens, 0.7 x model window)`) had only ever been unit-tested. Two live Mercury attempts with the threshold lowered to 2,500 tokens: the watcher ended the turn and the loop sent the handover prompt both times (`~/.orchestrator/mercury-race/2026-10-02-token-watcher-live`).
- **The handover itself failed, 2 of 2.** Mercury answered the handover prompt by carrying on with the task (edits, tests, a commit) and then replied `HANDOVER_COMPLETE` without writing `HANDOVER.md`, so the run escalated. Any Mercury run long enough to reach the real threshold would have ended this way.
- **Fix, in the Mercury adapter's handover turn** (`OpenAICompatWorkerSession.run_turn(checkpoint=True)`): `write_file` and `edit_file` refuse every path but `HANDOVER.md` and say why; a final answer without a `HANDOVER.md` written in this turn (a leftover from an earlier leg does not count), or without the completion marker, is answered with what is missing, up to twice; after that the turn ends and the loop escalates as before. The Claude Worker is unchanged.
- **A second bug behind it, in the loop, for every Worker.** `_execute_handover` reloaded state into its own variable, so the main loop went on with its pre-handover copy and wrote it back on the next save: the handover record, the handover turn's usage and executor record, and the stagnation reset were all lost (the live run logged "leg 1" twice and ended with `handovers: []`). The function now returns the state it worked on and the loop continues with that. `HANDOVER.md` is also removed from the tree once the seed for the fresh session has been built from it, so the next leg's `git add -A` cannot commit it.
- Tests: the handover turn (nudge, write limit, stale document, marker, giving up) in `tests/test_openai_compat_worker.py`, and the first loop-level handover test, `test_handover_survives_into_the_fresh_leg`.

### Worker worktree path guard (2026-09-10)
- **`build_worktree_guard(project_dir)`** in `orchestrator/worker.py`: an SDK `can_use_tool` callback wired into every `ClaudeAgentOptions` a Worker gets. It resolves the target `file_path` of any `Write`, `Edit`, `NotebookEdit`, or `MultiEdit` tool call against `project_dir`'s realpath and hard-denies (with `interrupt=True`, escalating rather than silently continuing) any path that resolves outside it, whether via an absolute path pointing at another checkout or a `../` relative escape.
- Closes the 2026-08-01 bug report: a Worker given a prepared worktree via `--project` once edited the repo's main checkout instead. `cwd` only sets the SDK subprocess's *starting* directory; it never constrained where a later absolute-path Edit/Write call landed. `can_use_tool` runs before every tool call, so this is a true per-call assertion, not a post-hoc reconcile check.
- Deliberately scoped to the SDK's structured file-editing tools (the ones that carry an explicit `file_path`). It does not, and cannot cheaply, guard a Bash command that writes outside `project_dir` (that needs shell parsing/simulation, a materially bigger feature); the existing git-based reconcile step remains the backstop for Bash-driven edits made inside `project_dir`'s own repo.
- 8 new tests in `tests/test_worker.py` (allow-inside, allow-relative-inside, deny-absolute-outside incl. interrupt+message assertions, deny-`../`-escape, Bash passthrough, no-`file_path`-input passthrough, and that `build_worker_options` actually wires `can_use_tool`). 459/459 tests green; `ruff check` clean.

### Best-of-N: held-out-certified selection (Wave 2 L8) (2026-06-25)
- **`orchestrator/best_of.py`** (`run_best_of_n(cfg, n)`): a THIN orchestration layer over the existing single-attempt machinery. It calls `run_orchestrator` N times, each in its OWN git worktree / branch (`orchestrator/<task-id>-attempt-<k>`, reusing `worktree.py`), collects each attempt's terminal `State`, and selects a winner. NOT a new execution engine: the Worker / Decision-Proxy / Marlin-Proxy loop is unmodified (proven by `git diff --name-only master`). Sequential attempts for this first slice (documented); the per-run token cap + the fleet daily cap are honored per attempt (shared `orchestrator_home` ledger).
- **Held-out-certified selection (the heart)**: from the cohort, ONLY attempts that reached `completed` AND whose held-out gate PASSED (`last_held_out.status == "pass"`) are eligible; the winner is the one with the LOWEST `time_to_verified_ms` (sum of every iteration's `worker_ms + proxy_ms`, the north-star metric), tie-broken by attempt index. NEVER selects by the Worker-visible in-tree `last_verify`. Zero held-out-green => escalate, no selection. A held-out fail only removes that attempt; it is NEVER fed back as a Worker retry.
- **Hard gate (the reason it ships)**: best-of-N exists ONLY because a trustworthy out-of-reach signal exists; without one it would just amplify the most convincing reward-hack. So if NO held-out is resolvable (no registry `held_out_verify`, no `--held-out`), `run_best_of_n` REFUSES up front and runs ZERO attempts. A non-git project (no per-attempt isolation possible) is refused too; a malformed registry fails loud.
- **`--best-of N` CLI flag** on `orchestrator start`: 1 (default) is the unchanged single-attempt path (byte-for-byte; `else: run_orchestrator(cfg)`); >= 2 routes to `run_best_of_n`. Composes with `--held-out`, `--worktree` (implied per attempt), and the stakes gate (a tier-3+ repo still needs `--confirm-stakes`; best-of-N does not relax it).
- **Typed cohort record**: `CohortAttempt` + `CohortResult` (`{branch, status, held_out, time_to_verified_ms, selected}` per attempt + the cohort's `selected_branch` / escalation reason), written to `<state_dir>/cohort.json` and emitted as `types/cohort.d.ts` by `scripts/gen_state_dts.py` (third contract alongside state + events; same pure-Python emitter). Drift-tested in `tests/test_state_dts.py` (prove-then-revert). A cohort-level event over L7 `events.py` is left as a clean seam (events projects one State; a cohort spans N). 450 tests green; ruff clean.

### Normalized event stream over State (Wave 2 L7) (2026-06-25)
- **`orchestrator/events.py`**: a flat, typed `Event` (`task_id`, `seq`, `iteration`, `ts`, `type`, `summary`, `data`) with a 10-member `EventType` Literal (`dispatched`, `iteration`, `decision`, `verify`, `held_out`, `tamper`, `stagnation`, `handover`, `escalation`, `terminal`). `project_events(state)` is a PURE, deterministic, total projection over the existing `State`: it changes nothing in the control loop, adds no write path, never mutates `State`. Ordered by iteration then a fixed kind order; surfaces the board-critical signals (held-out reward-hack fingerprint, tamper paths, stagnation, terminal status + exit_reason) and is provenance-faithful (`decided_by=system` machine ground truth stays distinct from Worker self-report in the payload).
- **`orchestrator events` CLI** (read-only): `--task-id <id>` emits one task's normalized stream as JSONL; `--all [--since <ISO>]` emits the merged, time-ordered stream across every task. Pure read (load -> project -> print); a corrupt state.json is skipped with a stderr warning, never corrupting the JSONL.
- **Typed contract**: `scripts/gen_state_dts.py` now ALSO emits `types/events.d.ts` (the `EventType` alias + `Event` interface, `data` dict as a `{ [key: string]: unknown }` index signature). Same self-contained pure-Python emitter, no node toolchain, no new dependency. A drift test (`tests/test_state_dts.py`) byte-diffs the committed contract and reddens on any `Event` change (verified by prove-then-revert). 433 tests green; ruff clean.
- **`types/state.d.ts` codegen** (`scripts/gen_state_dts.py`): a self-contained pure-Python emitter walks `State.model_json_schema()` and emits a typed `.d.ts` (one `export interface` per model, named `export type` unions for the four `Literal` aliases, `?` for optional/nullable fields, ISO datetime as `string`, arrays as `T[]`). No node toolchain, no new dependency. A drift test (`tests/test_state_dts.py`) regenerates into memory and byte-diffs the committed file, so `uv run pytest` fails the moment the model changes without a regenerate (verified: a temp field on `State` reddens the test). The future Kanban board reads state.json against this contract and can never silently drift from the source of truth.

### Hexagonal executor ports E4b: the Claude vs Mercury race, Mercury wins (2026-09-28)
- **`bench/mercury-race` + `scripts/mercury_race.py`**: 10 precisely specified goals on a seed project, hidden tests proven fair against reference solutions, installed into a verifier vault outside every repo; each goal run as a Claude and a Mercury cohort (best-of-2), scored against the pre-registered criterion (unit-tested).
- **Verdict**: both cohorts 10/10 held-out green; median time to verified Mercury 15.0s, Claude 28.6s; Mercury about 29x cheaper; Mercury has a multi-iteration tail (2 of 20 attempts failed hidden tests). Plan completed.
- **Audit trail**: the Mercury Worker now writes every tool call to `worker-tools.jsonl` next to `state.json`.

### Hexagonal executor ports E4a: the Mercury worker adapter behind the gate (2026-09-28)
- **`adapters/openai_compat_worker.py`**: an OpenAI-shaped tool loop over the secrets-proxy provider forward (streaming), with confined `read_file` / `write_file` / `edit_file` / `list_dir` / `run_command` / `update_state` tools. One shared path check (`worker.path_outside_root`) for both adapters; `run_command` under the denylist with a scrubbed env.
- **The E4 gate**: an `inception` worker is refused at startup unless the run has a held-out verifier (registry or `--held-out`). A provider failure fails the run; it never falls back to Claude.
- **Telemetry**: per-call TTFT, generation, tool time and Inception's own server latency (`CallLatency.server_ms`). Provider errors carry an explicit `transient` flag the retry classifier honors first. Mercury pricing added.

### Mercury transport: secrets-proxy provider forward (2026-09-28)
- **The Mercury path was dead**: it POSTed to the secrets proxy's `/raw`, which the proxy refuses by design (501), so every Mercury recon silently fell back to Claude. It now uses the proxy's provider forward (`POST /forward/inception/chat/completions`, secrets-proxy#21): only the chat body crosses, the proxy owns the upstream URL and the key location.
- **Key in place without a human step**: `INCEPTION_API_KEY` copied server-side into the Agentic OS Platform project's new `/providers` folder (fingerprint-matched, HTTP 200). The synthetic `INCEPTION_PROJECT_ID` default and the other Infisical coordinates are deleted from this repo.
- Shared `proxy_token.resolve_proxy_token` (0600 file first) for every proxy caller; `MERCURY_MODEL_ID` fixed to `mercury-2`.

### Hexagonal executor ports E3: executor telemetry (2026-09-28)
- **Per-call latency decomposition**: `ExecutorRecord` (replaces `ReconRecord`) appended to `state.executor_records` per Worker turn and per recon call, with `CallLatency` rows (`response_ms`, `ttft_ms`, `generation_ms`, `tool_ms`, `output_tokens`) and rollups; `None` where a provider does not expose a figure, never a fake zero. The Claude adapter measures response and tool time; `orchestrator status` shows one `executor:<role>` line.
- **Token over-count fixed**: the Claude CLI emits one assistant message per content block, each repeating the call's usage, and the turn's result total was added on top, inflating recorded tokens, the token caps and the cost estimate. Usage is now deduplicated per model call.
- **`cost_ceiling_usd` removed** (never enforced), rejected at load with a pointer to `--max-cost-usd`. Tests now isolate the operator config home.

### Hexagonal executor ports E1+E2 (2026-09-28)
- **WorkerPort seam** (`ports.py`, `adapters/`): the control loop now talks to the Worker through a provider-neutral `WorkerSession`/`WorkerAdapter` protocol pair; the Claude Agent SDK moved into `adapters/claude_worker.py` (byte-for-byte default behavior, same options/hook isolation/env contract). Adapter selection (`adapters.resolve_worker_adapter`) is a literal table keyed by provider, NOT a plugin registry; a non-Claude worker provider is refused loudly at startup (the E4 best-of-N + held-out gate still guards non-Claude code-writing). Plan: `docs/plans/2026-07-24-hexagonal-executor-ports.md`.
- **Explicit `provider` + `reasoning_effort` on `ExecutorProfile`**: any non-default model must name `provider = "anthropic" | "inception"` in `[executors.<role>]`; routing is never inferred from model-id strings. `reasoning_effort` (`instant|low|medium|high`) is Inception-only, threaded into the Mercury request body.
- **Recon seam wired live, config-gated** (E1): when `[executors.recon]` exists, `run_orchestrator` runs one read-only recon question about the goal before the first Worker turn and prepends the findings (advisory) to the Worker's first message; telemetry on `state.last_recon`. No `[executors.recon]` table => zero extra model calls. Written 2026-07-24 on PR #14 (closed unmerged), revived and rebased onto main 2026-09-28. 470 tests green.

### Wave 2 per-role executor seam + Mercury recon (2026-06-20)
- **`ExecutorProfile` + `resolve_executor(role)`** (`executor.py`): an operator-owned `[executors.<role>]` config in `~/.config/orchestrator/config.toml` maps a ROLE (worker/recon/planner) to a model + `auth_mode` + optional `cost_ceiling_usd`. With NO config every role resolves to Claude (`claude-opus-4-8`, subscription) -- byte-for-byte the current single-model behavior. Call sites speak in roles; model names never leak in. Not goal-frontmatter, not a per-repo registry field (same trust posture as the Marlin Proxy config). Malformed config fails loud.
- **Mercury (Inception) read-only recon** (`run_mercury_recon`, wired via `orchestrator.run_recon`): the one non-Anthropic path, recon ONLY. The Inception key is injected SERVER-SIDE on the ai-host secrets proxy (a dedicated raw-forward, NOT `/execute` which redacts + Ollama-summarizes and would corrupt a completion), so the orchestrator process and the transcript only ever see the completion text, never the key. Key/proxy unavailable => FAIL LOUD and fall back to Claude recon (tested). The Worker and BOTH Proxies stay Claude (asserted) -- recon is the only non-Claude surface this slice enables. `state.last_recon` records the `time_to_verified_result` telemetry (executor + wall-clock, logged, never gated). Ships DORMANT: nothing changes until an operator config points `recon` at Mercury. 400 tests green.

### Wave 0 reliability core + held-out verifier track (2026-06-19)
- **Wave 0 reliability core** (`7da7b6a`): the reliability spine the rest of the verifier sits on. 304 tests green at landing; full exit gate passes (`tests/test_wave0_exit_gate.py`).
- **Operator repo registry + held-out gate** (`repo_registry.py`, `held_out.py`): an operator-owned `~/.config/orchestrator/repos.toml` keyed by the project's REAL git remote (un-fakeable by the goal file) carries `held_out_verify`, `stakes_tier`, `allowed_mcp_servers`. On a stop-candidate, after the in-tree verify passes and the tamper tripwire clears, the held-out command (a test set outside the Worker's reach) runs: in-tree green + held-out red = the reward-hack fingerprint, escalates and is never retried.
- **`allowed_mcp_servers` as a per-repo ceiling** (`80841cb`): effective servers = safe defaults UNION (goal-requested INTERSECT registry ceiling). A goal can never enable a server the operator did not allow.
- **Worktree-per-attempt isolation** (`c094152`): opt-in `--worktree` runs the attempt in a dedicated git worktree with safe (never `--force`) cleanup.
- **`--held-out` flag + skill-driven dispatch** (`f5b430a`) and the end-to-end dogfood capstone (`982f544`): the live dogfood fired the fingerprint on a real `pin-to-clipboard` regression.
- **Stakes-tier dispatch gate** (this change): `stakes_tier >= 3` is now a real refusal, not a recorded note. `run_orchestrator` refuses to start (`status=stopped`, no Worker turn, zero token spend) unless the operator passes `--confirm-stakes` / `ORCHESTRATOR_CONFIRM_STAKES=1` (operator-owned, never goal-authored). The `autonomous-orchestration` skill forbids Claude from self-authorizing tier-3+. Composes with the always-on protections; does not relax `irreversible_ops`. Resolves the `orchestrator-tier3-dispatch-gate` backlog item. 371 tests green.

### v0.2.0: state reconciliation + token telemetry (2026-05-24)
- Per-iteration `git log` reconcile of commits / `git diff` reconcile of files; missing entries back-filled with `decided_by="system"`.
- `IterationUsage` capture from `AssistantMessage.usage` (input, output, cache_read, cache_create, model, worker_ms, proxy_ms).
- `baseline_ref` snapshot at orchestrator start.
- Schema break (no migration): `commits` and `files_touched` are now objects with provenance.
- Plan: `docs/plans/2026-05-24-orchestrator-v2-first-slice.md` (completed).

### terminal-state notifications (2026-06-07)
- `orchestrator/notify.py`: best-effort, fail-safe ping on every terminal state (`completed | escalated | stopped | failed`) so detached runs stop finishing silently. Three independent channels: macOS banner + sound (osascript); a webhook POST when `ORCHESTRATOR_NOTIFY_URL` is set (ntfy / Pushover / Slack); and Telegram via the secrets-proxy: the bot token + chat id are injected server-side from Infisical (Infrastructure project, `/monitoring`), so they never enter the process env or any caller context, and the run's reason text is shlex-quoted into the curl. Wired into `run_orchestrator`'s `finally` so it fires on every exit path including SDK-error failures; never raises. (At shipping time this channel was active when `SECRETS_PROXY_TOKEN` was present; the secrets-proxy caller-identity switch later replaced that shared token with the `secrets-proxy-call` CLI, which mints its own token from the operator's Infisical machine identity, so the channel is now active whenever the CLI is built.)
- The complementary "wake the dispatching session" path is a launch-method change, not code: the autonomous-orchestration skill now prefers the harness-tracked background launch (`run_in_background`) over `nohup`, so a Claude-dispatched run re-invokes the session on exit and the follow-up (review/merge/next) runs automatically. `nohup` stays documented for runs that must survive the session.
- 220/220 passing (13 notify tests, +4 for the Telegram channel); ruff clean. Tests isolate the notify side channels via an autouse conftest fixture so the suite never hits the live proxy/webhook.

### auth-mode env contract + cost guard (2026-06-07)
- Theme 3 shipped: `_scrub_anthropic_api_key` generalized into `apply_env_contract(auth_mode)` in `worker.py`. A cross-provider deny-list (OpenAI / Gemini / Google / Groq / Mistral / Cohere keys + `ANTHROPIC_AUTH_TOKEN`) is always scrubbed; `ANTHROPIC_API_KEY` is scrubbed only in `subscription` mode and KEPT in `api_key` mode. Scrubbed var names are logged to `run.log` (never values).
- New `AuthMode` (`subscription` | `api_key`), selectable via the `--auth-mode` CLI flag or per-goal `auth_mode` frontmatter (frontmatter wins). Motivated by the 2026-06-15 Anthropic billing change: headless/SDK use leaves the flat subscription for a metered credit then API rates, so blindly scrubbing the key would break the metered path.
- Cost guard in `guardrails.py`: `estimate_cost_usd` (per-model price table, cache-aware) + `cost_cap_hit`. `state.estimated_cost_usd` is recorded every iteration and shown in `orchestrator status`. A hard USD ceiling stops the run; auto-applied at $20 in `api_key` mode, opt-in via `--max-cost-usd` otherwise (subscription is uncapped, where per-token cost is notional).
- 9 new tests; 207/207 passing; ruff clean.

### v0.1.x hardening (2026-05-10 to 2026-05-24)
- Shared-index edit discipline in `WORKER_SYSTEM_PROMPT` (commit `e2bb6ef`). Stops parallel Workers from inventing different STATUS.md formats.
- `ANTHROPIC_API_KEY` env scrub at SDK-spawn boundary (commit `8eed8d7`). Keeps Worker on subscription auth even when launcher is wrapped in `infisical run`.
- `uv tool install`-ready packaging (commit `9591d04`). PyPI project name `claude-code-orchestrator`; CLI shim `orchestrator`.
- Documentation skill at `~/.claude/skills/orchestrator-dispatch/SKILL.md`.
- README with secrets/auth, smoke test, state.json reference, troubleshooting (commit `5ca5988`).

### v0.1.0: dogfood proof (2026-05-09)
- Single Worker run wrote its own v2 plan.
- Validated SDK gotchas: `setting_sources=[]` for hook isolation, explicit JSON-schema for partial-arg MCP tools, nested role in transcript messages.

## In flight

### Marlin Proxy: layered autonomy (Phase 0 landed)
- A persona-driven layer on the Decision Proxy `escalate` path: mechanical decisions (merge-after-verify, branch cleanup, status, procedural) auto-approved, taste/scope/product/irreversible escalated.
- Modules: `config.py` (config.toml + per-task frontmatter + per-category modes, hard-wired `irreversible_ops` escalate), `ledger.py` (append-only JSONL + notes.md, agreement aggregation), `marlin_proxy.py` (single-shot persona call, kill-switch + context-saturation fast paths, fail-safe-to-escalate).
- Wired into `orchestrator.py` escalate branch; `autonomy_stats` in `state.json`; `orchestrator marlin-proxy review` CLI; `personas/marlin.md` grounded in mined transcript patterns.
- Defaults to `mode=off`. Rollout: off -> shadow (collect agreement data) -> live on safe categories -> Phase 4 self-improvement.
- Plan: `docs/plans/2026-05-27-marlin-proxy.md` (in-progress).
- [ ] Continue the Marlin Proxy rollout past Phase 0 (off -> shadow -> live on safe categories -> self-improvement); see `docs/plans/2026-05-27-marlin-proxy.md`. (2026-09-10)

### M9 sprint mode (orchestrator side of the Agentic OS milestone M9)
- Plan: `agentic-os-platform/docs/plans/2026-09-28-m9-sprint-worker-build.md` (M9's home). Step A, the context-size token watcher, is this repo's first slice; step B is `orchestrator sprint`.
- [x] DONE 2026-09-29: `orchestrator sprint` ran live on hermes through the Agentic OS (Claude slicing, three verified slices, handover documents in the tenant vault, the benchmark hidden tests green on the result); the first attempt found the wheel shipping without the default personas, fixed in #37.

### Hexagonal executor ports: Mercury worker follow-ups (plan completed 2026-09-28)
- E1 to E4 shipped; the E4b race verdict is "Mercury wins" on the benchmark (both 10/10 held-out green, median 15.0s against Claude's 28.6s, about 29x cheaper), with a tail of multi-iteration attempts. Details: `docs/plans/2026-07-24-hexagonal-executor-ports.md`, Verdict.
- [ ] Mercury Worker round two on real repositories before it does real work: pick the repos and their hidden test sets (Marlin), move the hidden tests to a separate OS user so the Worker cannot read them, rerun `scripts/mercury_race.py`-style cohorts, and gate the result on the same 10-point band. (2026-09-28)
- [x] DONE 2026-09-28: Cut the Mercury tail. Four causes found and fixed (an `update_state` duplicate bug, self-report bookkeeping, streams held open, stalled calls); 20 of 20 attempts now finish in one iteration, mean 29.2s. Details: the plan's night reality update.
- [x] DONE 2026-10-02: Recovered the Mercury per-call overhead the caller-identity CLI added. One `secrets-proxy-call forward-session` process per Worker session instead of a process and a token mint per model call; transport overhead per call back from a median of 662ms to 259ms, attempt median 15.7s (was 21.2s). Numbers: Shipped, "Mercury transport: one proxy CLI process per Worker session".

## Queued (v2 themes, prioritized)

Each theme is a candidate "next slice." Pick by urgency × leverage; the smallest-blast-radius ones are first.

### Theme 3: env-mode contract at SDK-spawn boundary
**Status:** shipped (2026-06-07). See the dated entry under Shipped.
**What shipped:** `apply_env_contract(auth_mode)` replaces `_scrub_anthropic_api_key`: it always scrubs foreign provider keys + `ANTHROPIC_AUTH_TOKEN`, scrubs `ANTHROPIC_API_KEY` in `subscription` mode, and keeps it in `api_key` mode (the 2026-06-15 metered-billing cutover made the auth choice load-bearing). The scrubbed set is logged to `run.log`. A paired cost guard (`estimate_cost_usd` + `cost_cap_hit`) was added in `guardrails.py` with a per-run USD ceiling.
**Not shipped (scoped out):** the full PATH / HOME / locale ALLOW-list sandbox. It is higher-risk (stripping a var the SDK needs would break runs) and the deny-list + auth-mode toggle already delivers the billing-safety win. Add the allow-list in a later slice only if env contamination beyond provider keys is actually observed.
**Evidence:** 2026-05-24 production failure (1 of 4 Workers failed on credit-balance error before the scrub landed); 2026-06-15 Anthropic headless-billing cutover.

### Theme 4: stagnation-streak loop detection
**Status:** queued.
**Problem:** Loop detection is the original spec's headline safety feature and has never fired in production because every successful run has been one iteration. We don't know whether the elaborate similarity detector (transcript diffing, embedding distance) would catch the failure modes that actually happen. The iteration cap is the only thing standing between a stuck Worker and a runaway token bill.
**Approach:** Defer the elaborate detector. Ship the smallest signal that survives contact: "no new files_touched AND no new commits AND no new decisions for N consecutive iterations" → Proxy receives an explicit `stagnation_streak` field and the persona escalates on streak ≥ 2. Layer LLM-based similarity later only if the cheap heuristic misses cases we observe.
**Blast radius:** Small. State-driven; no transcript diffing required.
**Evidence:** v0.1.0 report ("safety net we have not yet tripped"); v0.1.x open issues ("still untested in the wild").

### Theme 6: Proxy feedback loop / Worker self-audit
**Status:** queued. Builds on Theme 1 reconciliation (already shipped).
**Problem:** The Proxy reads what the Worker reported but cannot detect what was omitted. In the 2026-05-24 batch, 2 of 4 Workers committed real work without calling `update_state(kind="commit")`. The Proxy was making decisions on `commits: []` while the branch had real commits.
**Approach:** Surface the self-report vs reconciled delta to the Proxy each iteration via a `reporting_health: {self_reported_commits: 0, actual_commits: 1, ...}` block in the Proxy's state snapshot. Persona is updated to nudge the Worker (via `decision.text`) when health degrades. Cheap; uses existing channels.
**Blast radius:** Small.
**Evidence:** v0.1.x open issues; 2026-05-24 reporting gap.

### Theme 5: context-handover scaffold
**Status:** shipped (2026-06-06). Plan: `docs/plans/2026-06-06-context-handover-layer3.md`.
**What shipped:**
- `"handover"` added to `ProxyAction` (orchestrator-internal only, not LLM-emittable).
- `config.context_handover_tokens = 80_000` (proactive trigger, ~50% of 200k window). Hard escalation fallback remains at `context_saturation_tokens = 120_000`.
- `orchestrator/handover.py`: `build_handover_prompt`, `verify_handover_doc` (git-anchored, Layer 3), `seed_fresh_session_message`.
- `orchestrator.py`: proactive override on reply path when token threshold crossed; `_execute_handover` helper; `_HandoverSignal` exception for clean leg breaks; multi-leg outer loop capped at 10 legs.
- `state.handovers[]` now populated on every handover.
- 15 new tests, 168/168 passing.
**Not shipped (Phase B):** sub-goal boundary trigger (needs Theme 4 stagnation signals).
**Evidence:** Both field reports; original spec.

### Theme 7: `orchestrator batch` subcommand
**Status:** queued, deferred. Should not land before Themes 3, 4, 6 ship. Ergonomics on an unreliable substrate is premature.
**Problem:** The validated parallel-batch recipe is a 6-step bash incantation per task (`nohup`, `git worktree add`, manual goal-file authoring, manual cherry-pick). It worked but it's not a product. Friction increases with batch size.
**Approach:** Add `orchestrator batch` that takes a list of `(spec-slug, project-repo)` pairs, creates worktrees, materializes goal files from `goals/_template.md`, launches detached, prints a polling dashboard. Cherry-pick stays manual (gating logic out of scope).
**Blast radius:** Medium. New CLI surface; no control-loop changes.
**Evidence:** v0.1.x operational recipe; observed friction in 2026-05-24 batch.

## Open follow-ups (not full themes)

- **Tooling baseline bootstrap for new machines + co-op contributors.** Scope-discovered 2026-05-25: the original handover assumed `trello-cli` and a separate `printing-press` push were needed; in fact `printing-press` is upstream at `mvanhorn/cli-printing-press`, `trello` is a printing-press-generated binary already shipping via `Lola-Stories/trello-pp-cli`, and `Lola-Stories/bootstrap` already exists with a working contributor onramp. The remaining work is unifying `Lola-Stories/bootstrap` + `dotfiles/install.sh` into one profile-driven `marlinjai/bootstrap` repo so contributors and Marlin's own machines pull from the same source of truth without leaking personal data across profiles. Plan: `docs/plans/2026-05-25-unified-marlinjai-bootstrap.md` (status: in-progress; phases 1-3 landed, phases 4-5 queued). Handover that started this: `docs/handovers/2026-05-25-tooling-baseline-bootstrap.md`.
- [ ] Finish the unified `marlinjai/bootstrap` migration: phase 4 (custom profile multiselect) and phase 5 (Infisical enforcement); see `docs/plans/2026-05-25-unified-marlinjai-bootstrap.md`. (2026-09-10)
- **Orchestrator GitHub push.** Shipped 2026-05-25 at `https://github.com/marlinjai/orchestrator` (public, master at commit `f3ac8b2`). `uv tool install git+https://github.com/marlinjai/orchestrator` now works auth-free.
- **Retry-with-backoff on transient SDK errors.** Observed 2026-05-25 during the unified-bootstrap dispatch: two consecutive Worker launches died with `API Error: 529 Overloaded` on iteration 1, and the orchestrator marked the task `failed` rather than retrying. The SDK already raises a discoverable exception (`Exception: Claude Code returned an error result: success`) and the worker log carries the 529 string. Proposed fix in `worker.py` / `orchestrator.py`: catch the SDK exception, classify by error string (529, 503, network timeout, 504 = retryable; auth errors, credit-balance = terminal), retry with exponential backoff (e.g. 30s, 60s, 120s, 240s, 480s, give up after 5 attempts inside a single iteration). Surface the retry count + last error in `state.json` so operators can see what is happening without tailing `run.log`. Blast radius: small, localized to the SDK-spawn wrapper. Without this, every autonomous run during Anthropic load events fails and needs manual relaunch.
- **CHANGELOG.md.** No changelog yet. The README field reports are informal substitutes. If we publish to PyPI, this becomes load-bearing.
- **`/dispatch` slash command.** Research recommended it as optional. Skipped this session because most of the operator flow happens outside Claude Code. Add when there's a friction case for it.
- **Worker prompt nudge for `update_state(kind="commit")`.** The reconciler catches misses, but Worker-side reporting is still discretionary. Theme 6 surfaces the gap to the Proxy; the prompt itself could also be tightened to "call update_state IMMEDIATELY after each git commit, not at meaningful checkpoints." Small change with high signal/cost ratio.
- **Multi-iteration dogfood.** Every run to date has been 1 iteration. Theme 4 (loop detection) can't really be validated until we have one. Synthesize one (e.g. a task with a deliberately ambiguous scope that needs Proxy nudges to converge) to stress the loop.
- **Pro plan concurrency ceiling.** Three parallel Workers was fine. Five? Ten? Unknown. Worth measuring before recommending the pattern to anyone else.
- [ ] Design and prioritize an auto-handover / context-rot survival loop for long autonomous Worker runs: three layers were sketched (built-in auto-compaction, a described auto-handover, a production-hardened version) but never turned into a plan or goal spec. Needs a design pass and a priority call before implementation. (Stray fact from the same discussion, out of scope for this repo: a separate idea about routing the arbosano `/admin` agent, which hand-rolls a raw Anthropic API loop, through `claude -p` instead; that belongs on arbosano's own roadmap, not here.) (2026-09-10)
- [ ] Decide whether `docs/orchestrator-explained.html` (a standalone dependency-free HTML explainer for a colleague, written 2026-08-06) should be committed or deleted. It currently exists only as an untracked file in the main checkout at `~/software-dev/orchestrator` and would be lost on a `git clean`. (2026-09-10)

## Known unknowns (carry into future planning)

- Does `setting_sources=[]` survive when the Worker shells out to `git` in a project that has its own `.claude/settings.json`? Untested.
- Whether stagnation-streak (Theme 4) produces false positives on legitimately slow refactor turns. Needs one real multi-iteration run to validate.
- Whether the Pro plan's rate-limit signaling surfaces through the SDK in a way we can detect before hitting a hard 429. Currently we'd find out via failure.
