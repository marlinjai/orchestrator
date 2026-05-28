---
type: plan
status: in-progress
date: 2026-05-27
title: Marlin Proxy, a layered policy for replacing the mechanical 70% of human back-and-forth
tags: [orchestrator, autonomy, proxy, persona, telemetry]
summary: Add a "Marlin Proxy" layer on top of the existing Decision Proxy that handles mechanical approvals, status pings, and procedural questions autonomously, while escalating product/taste/scope decisions. Roll out in three phases (off, shadow, live) with per-task overrides, a runtime kill switch, and an append-only decision ledger so the policy is fully reversible and measurable.
---

# Marlin Proxy: layered autonomy for the orchestrator

## Why

Transcript analysis across recent planning sessions (lola-stories, framer-clone, orchestrator) classified user responses into five categories:

| Category | Share | Examples | Automatable? |
|----------|-------|----------|--------------|
| Pure approval | ~40% | "go ahead", "push it and open the PR", "ok lets go review and merge" | Yes |
| Status ping | ~15% | "progress?", "its runnung", "what are our next steps?" | Yes |
| Procedural | ~10% | "should we rebase against main?", "this session is finished, right?" | Yes |
| Scope addition | ~25% | "also each family should have pre-made voices", "ensure it genders correctly" | No |
| Taste / priority | ~10% | "Nee, machen wir anschließend", "die 27 ohne Rückfrage", "language is a whole research topic of its own" | No |

The first three categories (~65%) are mechanical reactions to a state the orchestrator already knows: verify is green, PR opened, plan agreed. The last two are product judgment that requires Marlin's actual taste, German UX nuance, and runway/priority context.

The existing Decision Proxy already returns `continue | replan | escalate | stop`. Today every `escalate` interrupts Marlin. A Marlin Proxy layer can pre-decide most of those escalations with a known policy, escalating only the genuinely ambiguous ones.

## What this is not

Not a replacement for the Decision Proxy. The Decision Proxy answers "what should the Worker do next." The Marlin Proxy answers "when the Decision Proxy says escalate, can we auto-approve based on a policy Marlin would have agreed with."

Not a new agent loop. It is a stateless single-shot persona call, same shape as `proxy.py`, on the escalation path only.

## Architecture

```
Worker -> Decision Proxy -> { continue | replan | escalate | stop }
                                          |
                                          v
                                   Marlin Proxy (new)
                                          |
                       +------------------+------------------+
                       v                  v                  v
                  auto-approve        auto-defer         escalate
                  (continue with     (stop, leave for     (interrupt
                   the proposed       Marlin tomorrow)     Marlin now)
                   action)
```

The Marlin Proxy reads three inputs:

1. The Decision Proxy's `escalate` payload (what the Worker is asking about).
2. The current `state.json` (decisions so far, commits, files touched, baseline ref).
3. The goal file frontmatter (plan-agreed scope, category whitelist).

It returns a `MarlinDecision` with `choice ∈ {auto_approve, auto_defer, escalate}`, a `category` tag, and a one-line `reason`.

### Categories (initial set)

| Category | Auto-policy when live | Trigger phrases / state |
|----------|----------------------|-------------------------|
| `merge_after_verify` | auto_approve | Verify green, PR opened, plan agreed merge |
| `branch_cleanup` | auto_approve | Branch already merged or marked stale in state |
| `status_fetch` | auto_approve, return state summary | Worker asks "should I report progress" |
| `procedural_workflow` | auto_approve with known answer | "should we rebase", "open PR now" |
| `scope_change` | escalate | Worker proposes work not in goal frontmatter |
| `product_decision` | escalate | UX, copy, German nuance, voice/persona |
| `risk_tradeoff` | escalate | Force-push, delete uncommitted work, drop tests |
| `irreversible_ops` | escalate (hard-wired, no mode override) | Prod migrations, Coolify deploys, Infisical secret rotation, DNS changes, destructive deletes |
| `context_saturation` | escalate or auto-handover | Worker's `tokens_in` crossed the threshold (default 120k); decision is "fresh context now" vs "ask Marlin" |
| `unknown` | escalate | Anything not classified |

Categories are loaded from a YAML config so adding new ones does not require a code change.

## Three-level toggle

The whole feature defaults OFF. Three independent toggles, evaluated in order, first-match wins:

### Level 1, global config

File: `~/.config/orchestrator/config.toml` (new). New section:

```toml
[marlin_proxy]
mode = "off"          # "off" | "shadow" | "live"
persona_path = "~/.config/orchestrator/marlin-persona.md"
ledger_path  = "~/.orchestrator/marlin-proxy-decisions.jsonl"

[marlin_proxy.categories]
merge_after_verify  = "live"
branch_cleanup      = "live"
status_fetch        = "live"
procedural_workflow = "shadow"
scope_change        = "escalate"
product_decision    = "escalate"
risk_tradeoff       = "escalate"
irreversible_ops    = "escalate"   # hard-wired, mode change ignored
context_saturation  = "shadow"     # promote to "handover" after Phase 1 data
unknown             = "escalate"

[marlin_proxy.thresholds]
context_saturation_tokens = 120000   # Ralph Loop "Dumb Zone" boundary
per_decision_timeout_ms   = 30000
```

Per-category mode override: `live`, `shadow`, or `escalate`. A live category auto-approves. A shadow category logs what it would have done and still escalates. An escalate category is hard-wired to always interrupt Marlin.

This lets us auto-pilot the mechanical 70% on day one while keeping taste categories permanently in `escalate` mode.

### Level 2, per-task frontmatter

Goal file can override mode for one specific run:

```yaml
---
task: clean up local worktrees
marlin_proxy: live
marlin_proxy_categories:
  branch_cleanup: live
  unknown: escalate
---
```

Use for low-stakes experiments (worktree cleanup, dependency bumps) before trusting the global default.

### Level 3, runtime kill switch

Reuses the existing orchestrator kill-switch pattern. Touching `~/.orchestrator/marlin-proxy.disabled` forces all subsequent decisions to `escalate`, regardless of config. Takes effect on the next decision boundary (seconds, not a restart).

Implementation: `guardrails.py` already checks for a kill file each iteration. Add a second check for the marlin-proxy kill file, set a flag, the proxy reads the flag.

## Shadow-mode rollout (the safety net)

Three phases, each gated on observed agreement rate.

### Phase 0, OFF (today)

No code change. Decision Proxy `escalate` still interrupts Marlin every time. Baseline.

### Phase 1, SHADOW (week 1 to 2)

Marlin Proxy runs on every escalation but its decision is never executed. It writes one row to the ledger:

```jsonl
{"ts": "2026-05-27T19:14:02Z", "task_id": "lola-fix-voice", "iteration": 4, "category": "merge_after_verify", "proxy_choice": "auto_approve", "proxy_reason": "verify green, PR opened, plan agreed merge", "actual_choice": "approve", "agreed": true, "tokens_in": 1840, "wall_ms": 920}
```

After 1 to 2 weeks of real orchestrator runs, a tiny review command (`orchestrator marlin-proxy review`) shows agreement rate by category, all disagreements verbatim, and suggested category mode flips.

### Phase 2, LIVE on safe categories (week 3+)

Flip `merge_after_verify`, `branch_cleanup`, `status_fetch` to `live` globally. Keep everything else in shadow or escalate. Continue to log every decision. If agreement drops below 95% on a live category for any reason, flip it back to shadow.

### Phase 3, expand based on data

Only categories with shadow-mode agreement above 95% over at least 20 decisions are candidates for promotion to live. Taste categories (`scope_change`, `product_decision`) likely stay in `escalate` forever, that is by design.

## Borrowed from Karpathy's autoresearch

Three specific patterns from `karpathy/autoresearch` make the design more robust:

1. **Append-only ledger plus revertible pointer.** The proxy decision ledger is append-only JSONL, never rewritten. Easy to grep, easy to diff, never corrupted. Matches `results.tsv` discipline.
2. **Hard wall-clock per iteration.** The Marlin Proxy has its own timeout (default 30s). If the persona call hangs or the LLM is slow, the decision auto-escalates rather than blocks the orchestrator loop. Matches autoresearch's "5 min target, 10 min kill."
3. **Externalize state, do not accumulate.** The persona reads `state.json` and the escalation payload, nothing else. No conversation history. Single-shot. Matches autoresearch's "no tee, grep what you need" context discipline.

What we explicitly do NOT borrow: the "never stop, never ask" rule. Karpathy can be fully autonomous because his loss function is numeric (`val_bpb`). Ours is "did Marlin approve." Escalation is the whole point.

## Borrowed from Anthropic's effective-harnesses guidance

Anthropic's own measured telemetry on Claude Code (per `anthropic.com/research/measuring-agent-autonomy`):

- 99.9th-percentile turn duration nearly doubled in late 2025, but the realized number is still ~45 min, not the marketed multi-hour "autonomy horizon."
- Median turn stays ~45 sec.
- Experienced users (750+ sessions) auto-approve in over 40% of sessions; new users sit around 20%.

What we take from this:

1. **Design for 30 to 90 min unattended bursts**, not unbounded overnight runs. The orchestrator's existing `--max-hours 0.75` default is already in the right zone; do not raise it as part of this plan.
2. **Portable "lab notes" memory.** Add an append-only `notes.md` per task (parallel to the JSONL ledger) where the Marlin Proxy writes one short human-readable line per auto-approval ("Phase 2 verify green, merged PR #87"). A future Worker reading the file can rehydrate context in under 30 seconds without parsing JSONL. Matches Anthropic's CHANGELOG-as-lab-notes pattern.
3. **Context-saturation as first-class escalation.** Add `context_saturation` to the category set (see table above). The orchestrator already records `tokens_in` per iteration in `state.json`; the Marlin Proxy reads it, and when crossing the configured threshold (default 120k, matches Ralph Loop's "Dumb Zone") it either auto-triggers a fresh-context handover or escalates, depending on the per-task config. This is invisible failure today (silent quality collapse); making it a category surfaces it.

## Runtime targets, the honest version

Three distinct measurements get conflated in vendor marketing. Separating them:

| Source | What it actually measures | Reading |
|--------|---------------------------|---------|
| Anthropic 99.9p turn duration ~45 min | One Worker turn at the slowest 0.1% | Per-turn ceiling, not per-task |
| METR "14.5h horizon" for Opus 4.6 | Tasks a human budgets 14.5h for, 50% success | Task-complexity unit, NOT 14.5h of agent runtime |
| Devin telemetry, 30 to 120 min per task | Closer-architecture comparison (Worker + harness) | Realistic per-task wall-clock |

The actual ceiling is not wall-clock. It is context bloat. Quality collapses past 100 to 150k tokens regardless of run length (Ralph Loop "Dumb Zone", confirmed by Anthropic harness guidance and autoresearch's "no tee" discipline). A 6-hour run with fresh-context handovers every 30 min works. A 45-min run that bloats to 200k tokens is already degraded. This is why `context_saturation` is a category and `--max-hours` is just a backstop.

### Three runtime patterns this plan supports

1. **30 to 90 min unattended burst per task** (v1 target, works today). One Worker, one goal, existing `--max-hours 0.75`. The Marlin Proxy removes the mechanical interrupts so the *felt* run length matches the *actual* run length. This is the realistic evening-hours productivity multiplier: 3 to 5 hours of mechanical progress unattended while Marlin focuses on the taste 30%.
2. **Parallel overnight batches, Karpathy-style** (Phase 3 onwards). Not one long run; 6 to 10 independent 30 min runs in parallel git worktrees, each scoped to one small spec, ledger-tracked. The orchestrator already supports this per `CLAUDE.md` ("one worktree per task, one goal file per task, nohup detached"). The unit is "spec," not "hyperparameter set."
3. **Continuous multi-day with fresh-context handovers** (Phase 5, research zone). Each Worker turn writes `notes.md` and exits. Next Worker reads `notes.md` + state, starts fresh. Ralph Loop's pattern. Not v1 scope, called out only so the architecture supports it later.

The framing for v1: not yet "Claude codes overnight while Marlin sleeps." It is "Claude makes 3 to 5 hours of mechanical progress unattended while Marlin focuses on the taste 30%." That delivers a 2 to 3x multiplier on evening output without entering the failure-prone autonomy zone.

**Long-term vision: overnight robot.** The north star is the autoresearch-style overnight loop: Marlin closes the laptop, comes back to 6 to 10 merged PRs, a refreshed ledger, and a self-improvement PR or two waiting for review. Phase 2 unlocks the 2 to 3x evening multiplier; Phase 3 unlocks parallel batches (the first credible "overnight" mode, bounded by per-task `--max-hours`); Phase 5 unlocks true continuous multi-day operation via fresh-context handovers. The intermediate phases are not detours from the vision, they are the only way to *earn* the trust that the overnight robot needs (ledger agreement data, self-improvement track record, allowlist discipline). Each phase is the prerequisite for the next.

## Phase 4, self-improvement loop (added)

Inspired by autoresearch's git-ratchet pattern, but with a strict `SELF_MODIFY_ALLOWLIST` so the control plane stays human-only.

### Self-modification targets, by risk class

| Target | Risk | Mechanism | Phase |
|--------|------|-----------|-------|
| `personas/marlin.md` (the policy prompt) | Low | Agent proposes edit, replays against historical ledger, opens PR with before/after agreement numbers | 4 |
| `config.toml` category modes (shadow to live) | Low | Ledger-review agent computes agreement rate, opens PR proposing a mode flip with evidence | 4 |
| `orchestrator/marlin_proxy.py` (classifier logic) | Medium | Worker proposes patch, full pytest passes, integration test on throwaway repo, then PR (human review required) | 4 |
| `orchestrator/orchestrator.py`, `proxy.py`, `worker.py` (control plane) | High | Hard-blocked, never auto-modified | Never |

Enforced via:

```python
# orchestrator/self_modify.py
SELF_MODIFY_ALLOWLIST = frozenset({
    "personas/marlin.md",
    "personas/default.md",
    "config.toml",
    # marlin_proxy.py added in Phase 4 once test coverage is sufficient
})
```

The Worker prompt for self-improvement tasks includes a hard rule: "You may only edit files in `SELF_MODIFY_ALLOWLIST`. Editing any other file is a guardrails violation and the run will be killed." The `guardrails.py` `bash denylist` mechanism extends to file paths.

### Self-improvement loop

Triggered weekly via `orchestrator marlin-proxy self-improve` (or by cron via the existing `schedule` skill):

1. Read the full ledger (`~/.orchestrator/marlin-proxy-decisions.jsonl`).
2. Compute per-category agreement rate over the last 30 days.
3. **For categories with agreement above 95% over 20+ shadow decisions**: open a PR flipping `shadow` to `live` in `config.toml`. PR body includes the agreement table and the 5 worst-disagreement examples (sanity check). Marlin reviews, merges or rejects.
4. **For categories with agreement below 80%**: dispatch a Worker on a goal file like "extract the disagreement pattern from the last 50 ledger rows on category X and propose a `personas/marlin.md` edit that would have changed the proxy's choice on at least 80% of disagreements." Worker edits `personas/marlin.md`, replays the historical ledger against the new persona, reports the new agreement rate. If new rate > old rate, open PR. If not, discard and try again next week.
5. **Git is the ratchet.** Same as autoresearch: a PR that improves measured agreement gets merged. A PR that does not gets closed. No agreement-rate regression ever lands.

### Why the control plane stays off-limits

Autoresearch can self-modify `train.py` because `train.py` is the *subject* of optimization, not the loop driving the optimization. The loop is fixed. Same discipline here: `personas/*.md` and `config.toml` are the subject (policy); `orchestrator.py` and `proxy.py` are the loop (control). An agent modifying its own control plane is the classic recursive self-improvement footgun; the allowlist makes it physically impossible until a human explicitly extends it.

### Phase 4 success criteria

- After 4 weeks of self-improvement runs, at least one category has been auto-promoted from shadow to live based on data, with the PR merged.
- At least one persona edit has landed that measurably improved agreement rate on a previously-disagreeing category.
- Zero PRs have attempted to modify files outside `SELF_MODIFY_ALLOWLIST` (allowlist enforcement works).
- Marlin's review time on these PRs is under 5 min each (PR bodies carry enough evidence to decide without re-reading the ledger manually).

## Borrowed from Ralph Loop

The Ralph Loop community converged on three explicit escalation triggers we should encode directly:

1. **Fuzzy success criteria** (no machine-verifiable judge): always escalate.
2. **Irreversible ops** (prod migrations, secret rotation, destructive deletes, anything touching Coolify, Infisical, DNS): always escalate, hard-wired, no mode override.
3. **Human-as-judge review** (taste, copy, UX): always escalate.

These map cleanly onto our existing `scope_change`, `product_decision`, `risk_tradeoff`, and the new `irreversible_ops` categories. The `irreversible_ops` category is the most important new addition: it is hard-wired to `escalate` and cannot be overridden by config or per-task frontmatter. Even if Marlin accidentally sets `live` on it, the proxy refuses.

## Autonomy-runtime metrics (free with this work)

The ledger gives us two metrics the orchestrator does not currently surface:

1. **Decisions between escalations.** Count of consecutive ledger rows with `choice != escalate`. Higher = more autonomous.
2. **Wall-clock autonomous runtime per task.** Sum of `wall_ms` across non-escalate decisions, until the first escalate.

Both go into `state.json` as a new field `autonomy_stats: { decisions_between_escalations: int, autonomous_runtime_ms: int }`, surfaced via `orchestrator status`. No new dashboard needed for v1.

## Files to create or modify

New:

- `orchestrator/marlin_proxy.py` (single-shot persona call, returns `MarlinDecision`)
- `orchestrator/config.py` (load `~/.config/orchestrator/config.toml`)
- `orchestrator/ledger.py` (append-only JSONL writer for proxy decisions)
- `personas/marlin.md` (the persona prompt, references `~/.claude/marlinjai.md` voice guide)
- `orchestrator/cli/marlin_proxy.py` (the `marlin-proxy review` subcommand)
- `tests/test_marlin_proxy.py` (unit tests on category classification and mode resolution)

Modified:

- `orchestrator/orchestrator.py` (call Marlin Proxy on Decision Proxy `escalate`)
- `orchestrator/state.py` (add `autonomy_stats` field)
- `orchestrator/guardrails.py` (add second kill-switch check)
- `orchestrator/cli/__init__.py` (register `marlin-proxy` subcommand)
- `CLAUDE.md` (one paragraph documenting the new layer)
- `ROADMAP.md` (mark this plan as in-progress when implementation starts)

## Test plan

Unit:

- Mode resolution (global vs per-task vs kill-switch order of precedence)
- Category classification on synthetic escalation payloads
- Ledger append is atomic and never overwrites
- Kill-switch flips all decisions to escalate within one decision boundary

Integration (against a real Worker on a throwaway repo):

- Run a "merge a green PR" task with global config `live` on `merge_after_verify`, verify no escalation reaches Marlin and the merge happens.
- Run a "rename a UI string" task, verify it escalates (category `product_decision`).
- Touch the kill switch mid-run, verify next decision goes to Marlin even though config says `live`.

## Open questions

1. **Persona definition.** The Marlin persona prompt has to encode the 70/30 taxonomy. Draft references `~/.claude/marlinjai.md` voice guide and the transcript analysis taxonomy table. Iteration likely needed after Phase 1 ledger data lands.
2. **Web research findings (folded in).** The 2026 sweep confirmed the 70/30 boundary is the same line Ralph Loop and Anthropic both draw. Two categories were added based on findings: `irreversible_ops` (hard-wired escalate, no override, covers Coolify/Infisical/DNS/prod), and `context_saturation` (escalate or auto-handover when `tokens_in` > 120k, mitigates Ralph Loop's "Dumb Zone"). Anthropic's measured 99.9p Claude Code turn duration is ~45 min, so the orchestrator's existing `--max-hours 0.75` default is already correctly sized; do not raise it as part of this plan. Cline's auto-approve-by-category pattern validated the configurable per-category mode design.
3. **Ledger review cadence.** Weekly via `orchestrator marlin-proxy review` for now. If agreement rate stays high, monthly. If it surfaces frequent disagreement on a "live" category, the category flips back to shadow immediately.

## Phasing summary

| Phase | What happens | Reversibility |
|-------|--------------|---------------|
| 0 | Code lands, mode=off | Trivial, code is dead |
| 1 | Mode=shadow on all categories | Touch kill file, or set mode=off |
| 2 | Mode=live on three mechanical categories | Per-category flip back to shadow |
| 3 | Expand live categories + parallel overnight batches | Same per-category flip |
| 4 | Self-improvement loop (persona + config edits as PRs) | Revert the PR |
| 5 | Multi-day continuous with fresh-context handovers (research zone, not committed) | n/a, future work |

The whole design is built so that any phase can roll back to the previous one in seconds via one config edit or one `touch`. No code redeploy needed to disable. Phase 4 PRs are also fully reversible via `git revert`. Control plane (`orchestrator.py`, `proxy.py`, `worker.py`) is never auto-modified at any phase.
