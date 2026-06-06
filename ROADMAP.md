# ROADMAP

Living tracker for orchestrator work. Read top to bottom: shipped at the top, in-flight in the middle, queued at the bottom.

## Shipped

### v0.2.0: state reconciliation + token telemetry (2026-05-24)
- Per-iteration `git log` reconcile of commits / `git diff` reconcile of files; missing entries back-filled with `decided_by="system"`.
- `IterationUsage` capture from `AssistantMessage.usage` (input, output, cache_read, cache_create, model, worker_ms, proxy_ms).
- `baseline_ref` snapshot at orchestrator start.
- Schema break (no migration): `commits` and `files_touched` are now objects with provenance.
- Plan: `docs/plans/2026-05-24-orchestrator-v2-first-slice.md` (completed).

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

## Queued (v2 themes, prioritized)

Each theme is a candidate "next slice." Pick by urgency × leverage; the smallest-blast-radius ones are first.

### Theme 3: env-mode contract at SDK-spawn boundary
**Status:** queued. Smallest slice; natural pairing with the existing `_scrub_anthropic_api_key`.
**Problem:** The scrub catches one variable. Any wrapper (Infisical, direnv, mise, parent shell exports) can mutate auth mode, MCP server discovery, hook resolution, or model selection silently. We patched one symptom; the class remains.
**Approach:** Generalize the scrub into an explicit env contract in `worker.py`. Allow-list (PATH, HOME, USER, LANG, locale, project-specific test runners) + deny-list (`ANTHROPIC_API_KEY`, `CLAUDE_*` legacy vars, `OPENAI_API_KEY` and other LLM provider keys to prevent cross-contamination). Log the scrubbed set to `run.log` so it's auditable.
**Blast radius:** Small. Single function, behavior already partially implemented.
**Evidence:** 2026-05-24 production failure (1 of 4 Workers failed on credit-balance error before the scrub landed).

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

- **Tooling baseline bootstrap for new machines + co-op contributors.** Scope-discovered 2026-05-25: the original handover assumed `trello-cli` and a separate `printing-press` push were needed; in fact `printing-press` is upstream at `mvanhorn/cli-printing-press`, `trello` is a printing-press-generated binary already shipping via `Lola-Stories/trello-pp-cli`, and `Lola-Stories/bootstrap` already exists with a working contributor onramp. The remaining work is unifying `Lola-Stories/bootstrap` + `dotfiles/install.sh` into one profile-driven `marlinjai/bootstrap` repo so contributors and Marlin's own machines pull from the same source of truth without leaking personal data across profiles. Plan: `docs/plans/2026-05-25-unified-marlinjai-bootstrap.md` (status: draft). Handover that started this: `docs/handovers/2026-05-25-tooling-baseline-bootstrap.md`.
- **Orchestrator GitHub push.** Shipped 2026-05-25 at `https://github.com/marlinjai/orchestrator` (public, master at commit `f3ac8b2`). `uv tool install git+https://github.com/marlinjai/orchestrator` now works auth-free.
- **Retry-with-backoff on transient SDK errors.** Observed 2026-05-25 during the unified-bootstrap dispatch: two consecutive Worker launches died with `API Error: 529 Overloaded` on iteration 1, and the orchestrator marked the task `failed` rather than retrying. The SDK already raises a discoverable exception (`Exception: Claude Code returned an error result: success`) and the worker log carries the 529 string. Proposed fix in `worker.py` / `orchestrator.py`: catch the SDK exception, classify by error string (529, 503, network timeout, 504 = retryable; auth errors, credit-balance = terminal), retry with exponential backoff (e.g. 30s, 60s, 120s, 240s, 480s, give up after 5 attempts inside a single iteration). Surface the retry count + last error in `state.json` so operators can see what is happening without tailing `run.log`. Blast radius: small, localized to the SDK-spawn wrapper. Without this, every autonomous run during Anthropic load events fails and needs manual relaunch.
- **CHANGELOG.md.** No changelog yet. The README field reports are informal substitutes. If we publish to PyPI, this becomes load-bearing.
- **`/dispatch` slash command.** Research recommended it as optional. Skipped this session because most of the operator flow happens outside Claude Code. Add when there's a friction case for it.
- **Worker prompt nudge for `update_state(kind="commit")`.** The reconciler catches misses, but Worker-side reporting is still discretionary. Theme 6 surfaces the gap to the Proxy; the prompt itself could also be tightened to "call update_state IMMEDIATELY after each git commit, not at meaningful checkpoints." Small change with high signal/cost ratio.
- **Multi-iteration dogfood.** Every run to date has been 1 iteration. Theme 4 (loop detection) can't really be validated until we have one. Synthesize one (e.g. a task with a deliberately ambiguous scope that needs Proxy nudges to converge) to stress the loop.
- **Pro plan concurrency ceiling.** Three parallel Workers was fine. Five? Ten? Unknown. Worth measuring before recommending the pattern to anyone else.

## Known unknowns (carry into future planning)

- Does `setting_sources=[]` survive when the Worker shells out to `git` in a project that has its own `.claude/settings.json`? Untested.
- Whether stagnation-streak (Theme 4) produces false positives on legitimately slow refactor turns. Needs one real multi-iteration run to validate.
- Whether the Pro plan's rate-limit signaling surfaces through the SDK in a way we can detect before hitting a hard 429. Currently we'd find out via failure.
