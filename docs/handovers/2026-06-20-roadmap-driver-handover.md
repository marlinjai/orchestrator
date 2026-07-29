---
type: handover
title: "Driver handover: Wave 1 remainder -> Wave 2 Mercury seam -> Wave 3 Kanban control plane"
date: 2026-06-20
summary: >
  Self-contained brief for a driver agent (T) to take the Autonomous Dev Platform
  roadmap from the current state (Wave 0 + verifier + drift-loop done) through the
  Wave 1 glue remainder, the Wave 2 per-role-model (Mercury) seam, and the Wave 3
  Kanban control plane + planning agents + best-of-N + discovery feeder. Encodes the
  leaf dependency DAG (parallel where independent, sequential where forced) and the
  rule to dispatch bounded buildable leaves through the orchestrator itself.
tags: [orchestrator, roadmap, handover, multi-model, mercury, kanban, control-plane, driver]
projects: [orchestrator, knowledge-base]
---

# Handover: drive the roadmap to the Kanban control plane (driver agent T)

You are T, the driver. Your job is to take the remaining Autonomous Dev Platform
roadmap to done: finish Wave 1 glue, ship the Wave 2 per-role-model (Mercury) seam,
then build the Wave 3 Kanban control plane (the "Kanban bot") with its planning
agents, best-of-N, and proactive discovery feeder. Maximize parallelism on
independent leaves, sequence the dependent ones, and BUILD ON TOP OF THE ORCHESTRATOR
(the autonomous driver) by dispatching each self-contained buildable leaf as a goal
rather than hand-coding everything yourself. You coordinate; the orchestrator executes.

## 0. Orient (read before doing anything)

- ROADMAP source of truth: `~/software-dev/knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md`
- This repo: `~/software-dev/orchestrator` (read `CLAUDE.md` + `ROADMAP.md`). Tests: `uv run pytest -q`. Lint: `uv run ruff check orchestrator/ tests/`. `python` is NOT on PATH, always `uv run`.
- Decision context: `docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md` (the multi-model/Mercury call, section 4) and `docs/handovers/2026-06-19-verifier-track-handover.md`.
- The first Wave-2 leaf is already scoped: `goals/orchestrator-executor-profile-mercury-recon.md`.
- Goal-spec format: `goals/_template.md`. Operator playbook: `skills/autonomous-orchestration/SKILL.md`.

## 1. Already done (do NOT redo)

- Wave 0 reliability core: stagnation brake, SDK retry-backoff, ground-truth-to-Proxy + injection hardening, usage cap + global kill, tamper tripwire. MERGED to master.
- Trust anchor + held-out verifier (operator repo registry, held-out gate), allowed_mcp_servers ceiling, worktree-per-attempt isolation, the tier-3 dispatch gate. MERGED to master (371 tests green).
- The drift loop: capture/sweep/roadmap run as a closed loop on every session start + stop (bootstrap repo: SessionStart hook + capture-drain renders the views).

So the engine and its trust prerequisites exist. Both multi-model gates are now satisfiable: (a) held-out verifier exists + validated on a real repo; (b) the secrets proxy is the route for non-Anthropic keys.

## 2. The leaf DAG (parallel where independent, sequential where forced)

Phase 1 -- start ALL of these in parallel (no cross-dependencies):
- L1  drain-lib.sh extraction: factor the proven capture-drain machinery into a reusable lib so each new drain is a ~20-line caller. (bootstrap repo)
- L2  closed-loop-sync reconcile dead-seam: flip `closed-loop-sync/cli.py` reconcile `SystemExit` to wire the already-tested engine (judge stays None).
- L3  state.d.ts typed state contract: codegen TS types from the Pydantic `State` so the Wave-3 board can never drift from `state.json`. THE KEYSTONE for the board.
- L4  ExecutorProfile + Mercury recon: build `goals/orchestrator-executor-profile-mercury-recon.md` (defaults to Claude; Mercury read-only recon via the proxy; no Worker/Proxy on a non-Claude model).
- L5  proactive discovery feeder: re-home product-evolution's researcher + strategist as a weekly drain that drops value/cost-scored intent stubs into `backlog/intents/`. Feeds the backlog, NEVER dispatches.

Phase 2 -- each starts only after its Phase-1 dep has MERGED:
- L6  release-as-PR drain (after L1): on a `completed` run, open a version-bump PR + Telegram nudge. Do NOT auto-publish (npm publish is Tier-4, human-only).
- L7  normalized event stream (after L3): the board's data layer over the typed state contract.
- L8  best-of-N (after L4): cheap on subscription, GATED on the held-out verifier (exists). Selection certified by held-out-green, never by a Worker-visible signal.

Phase 3:
- L9  the board on ai-host (after L7): API-first, mobile kanban. Drag-to-dispatch, drill into the live event stream, approve/deny, SSH-resume escape hatch (`claude --resume <session-id>` in tmux). Reuse the intelligence-platform Phase-2 design. Approve/merge DISABLED on any `completed` lacking held-out-green; every card surfaces held-out status + tamper paths + stagnation.

Phase 4:
- L10 planning / routing agents (after L9): create tickets and pick the execution strategy by complexity (single Worker / best-of-N / agent team). This is the Vibe-Kanban moat and the genuine differentiator.

## 3. Use AGENT TEAMS -- T is the conductor, not a serial worker (MANDATORY)

Do NOT work the leaves one at a time yourself. You are the conductor of an agent
team. Fan out; do not grind. There are TWO layers of parallelism, use both:

- LAYER A (your team): spawn one sub-agent PER INDEPENDENT LEAF via the Agent tool,
  ALL IN A SINGLE MESSAGE (multiple tool calls in one turn) so they run concurrently.
  Give each sub-agent `isolation: "worktree"` so their parallel file mutations never
  collide. Use a read-only Explore agent for recon/localization leaves; a
  general-purpose/build agent in a worktree for building leaves. For a large,
  structured fan-out + adversarial-verify pass, a Workflow is the right tool; for a
  handful of leaves, parallel Agent calls are enough.
- LAYER B (the orchestrator): each build sub-agent BUILDS ON TOP OF THE ORCHESTRATOR
  (the free-running autonomous driver) by dispatching its leaf as a verify-gated goal
  (Worker + Decision Proxy + held-out gate), rather than hand-coding it. Reserve
  direct hand-coding for refactors where dispatch is awkward (e.g. the orchestrator
  editing its own source). The orchestrator can itself run parallel Workers (the
  batch pattern); your team is the coordination layer above it.

Conductor loop, per phase:
1. For each leaf in the phase, write `goals/<leaf-id>.md` (template format). Encode
   `depends_on: [<leaf-id>, ...]` (a dep must MERGE before the dependent launches) and
   `shared_state` tags where two leaves touch the same surface.
2. Spawn the phase's independent leaves as a parallel agent team (one message, one
   worktree-isolated sub-agent each). Each sub-agent: build the leaf (dispatch via the
   orchestrator or implement in its worktree), keep the verify gate green
   (`uv run pytest -q && uv run ruff check orchestrator/ tests/`, adapt per repo),
   single conventional commit, open a DRAFT PR, and REPORT BACK the PR link + status.
3. For each finished leaf, spawn a fresh reviewer/verifier sub-agent (independent
   context, refute-stance) to adversarially check it before you call it done. This
   composes with the held-out verifier; it does not replace it.
4. Collect the team's results. You do NOT merge (human gate). Hold every Phase-2+ leaf
   until its Phase-1 dependency PR has MERGED, then spawn the next phase's team.

After L4 lands, the coordinator/recon role may run on the cheap/fast executor per the
ExecutorProfile split; the Worker and both Proxies always stay Claude.

## 4. Hard constraints (do not violate)

- TWO permanent human gates: DISPATCH (Marlin picks scope) and MERGE (into product/revenue repos). Everything between is automatable.
- The orchestrator's own repo is high-stakes: any autonomous run on it needs `--confirm-stakes` with Marlin's EXPLICIT go. NEVER self-authorize tier 3+.
- Do NOT build: model registry, provider adapters, ADR system, eval framework, auto-merge, auto-publish, microVM/gVisor now, a trained reward model, the local-Qwen engine, a DAG engine inside the board.
- Non-Anthropic keys (Mercury/Inception, Gemini) route SERVER-SIDE through the secrets proxy on ai-host, never into a Worker transcript. Default every role to Claude.
- Gate on reversibility/stakes, never on agent self-reported confidence (logged, never gated). The one decision metric is `time_to_verified_result`, never tokens-per-second.
- Billing flat (subscription). No em-dashes / en-dashes. Conventional commits. `uv run pytest` + `uv run ruff check` green after every change. Commit/push only when Marlin asks.

## 5. Definition of done (the whole arc)

- Wave 1 closed: drain-lib factored, reconcile seam live, release-as-PR drain shipping draft PRs, state.d.ts generated and consumed.
- Wave 2 closed: ExecutorProfile seam live (defaults to Claude), Mercury read-only recon via the proxy, best-of-N gated on the held-out verifier.
- Wave 3 live: the Kanban control plane on ai-host renders the live event stream, drag-to-dispatch, approve/deny gated on held-out-green, SSH-resume escape hatch; planning/routing agents create tickets and pick strategy by complexity; the discovery feeder drops scored stubs weekly.
- Every leaf: tests green, ruff clean, draft PR (never auto-merged), ROADMAP "Shipped" updated in the existing format.

## 6. First action

Write goal specs for L1-L5 (L4's exists), then spawn the Phase-1 agent team: FIVE
worktree-isolated sub-agents in a SINGLE message, one per leaf, running concurrently.
Each builds its leaf (dispatching through the orchestrator where it fits), keeps verify
green, and opens a draft PR. Surface to Marlin for DISPATCH approval and (for any
orchestrator-repo run) `--confirm-stakes` before dispatching. Then a reviewer sub-agent
per finished leaf. Do not start a Phase-2 leaf until its Phase-1 dependency has merged.
