---
type: handover
title: "Wave 0 reliability core (in flight) + multi-model integration decision"
date: 2026-06-18
summary: >
  Resume point for the orchestrator Wave 0 reliability-core work (branch
  feat/wave-0-reliability-core, uncommitted) and the strategic decisions from the
  long planning conversation that produced it: the autonomous-dev-platform roadmap,
  the multi-model / Mercury 2 integration call, and the manual-mode skills layer.
tags: [orchestrator, wave-0, reliability, multi-model, mercury, handover, skills]
projects: [orchestrator, knowledge-base]
---

# Handover: finish Wave 0, hold the multi-model line

You are picking up mid-stream. A long planning conversation produced a roadmap and
started implementing the orchestrator's reliability core. Your job: **finish Wave 0
exactly as scoped, keep the suite green, do not start the multi-model work.**

## 0. Orient first (read these)

- Roadmap (source of truth): `~/software-dev/knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md`
- Billing reality (a prior assumption was falsified): `~/software-dev/knowledge-base/research/2026-06-17-anthropic-agent-sdk-metering-deferred.md` (Anthropic DEFERRED the 2026-06-15 Agent-SDK metering; Claude-on-subscription is FLAT-rate again, advance notice before any change).
- This repo: `~/software-dev/orchestrator`, branch **`feat/wave-0-reliability-core`** (uncommitted), tests run with **`uv run pytest -q`**, lint with **`uv run ruff check orchestrator/ tests/`** (`python` is NOT on PATH; always use `uv run`).

## 1. Current state of the work tree (verify with `git -C ~/software-dev/orchestrator status`)

**258 tests pass, ruff clean.** Shipped this session (all uncommitted on the branch):

| Step | Files | What |
|---|---|---|
| Stagnation brake | new `orchestrator/stagnation.py`, new `tests/test_stagnation.py`, `state.py` (+`stagnation_streak`, `last_progress_key`), `orchestrator.py` (wired after reconcile, resets on handover) | Progress fingerprint = plan-step / decision / verify movement, NEVER git churn (a no-op commit can't game it). Streak >= cap (default 3) -> hard-stop + the existing cheap `notify`, never a fresh Proxy call. |
| SDK retry-with-backoff | new `orchestrator/retry.py`, new `tests/test_retry.py`, `state.py` (+`transient_retries`), `orchestrator.py` (leg loop changed `for`->`while`; transient 529/rate-limit/network errors back off and retry the SAME leg without consuming a handover leg; real errors still fail) | Overnight runs no longer die on a transient 529. |
| Ground-truth to Proxy + injection hardening | `orchestrator.py` (`_run_one_turn` no longer calls the Proxy; the loop reloads+reconciles git, THEN calls the Proxy), `proxy.py` + `marlin_proxy.py` (system prompts hardened; prompts add a machine-computed GROUND TRUTH section; Worker-authored text fenced under an UNTRUSTED banner), `state.py` (new shared `ground_truth_summary(state)` used by both proxies), `tests/test_orchestrator.py` (rewrote mocks: `_run_one_turn` now returns `(chunks, usage)`, proxy is patched separately), `tests/test_proxy.py` + `tests/test_marlin_proxy.py` (added hardening tests) | Fixes the confirmed production failure (Proxy decided on `commits:[]` while the branch had commits). Both proxies now decide on machine-provenance facts (git reconcile counts, verify exit code), not Worker prose. A Worker can't inject a decision into the judge. |

Task tracker state: stagnation (done), backoff (done), ground-truth+injection (done). Remaining below.

## 2. What remains in Wave 0 (your job)

1. **Usage/iteration cap + global kill.** The dollar cost guard already exists (`guardrails.estimate_cost_usd` + `cost_cap_hit`, default off). Add a rate-limit-aware cumulative usage/iteration ceiling + a global daily kill above the per-run guard. Keep the dollar cap present but default OFF (billing is flat now). Surface in `orchestrator status`.
2. **Cheap tamper tripwire in the verify gate.** In `verify.py` / `reconcile.py`: before accepting a verify pass, git-diff test files and the verify command's own targets vs `baseline_ref`; flag DELETED tests / dropped assertion counts as a signal, downgrade pass -> escalate when the strong fingerprint appears. Path-touched is a LOG signal only (avoid a false-positive storm: legit work edits tests constantly). Record `tamper_paths` on State for the Proxy. NOTE: the full held-out verifier is Wave 2; this is only the cheap tripwire.
3. **(lower urgency, bootstrap repo not this repo) Recursion guard:** in `on-session-stop.sh`, OR every `*_HEADLESS` flag into the capture-enqueue guard. Precondition for Wave 1's second headless drain; no second drain exists yet, so this can wait.

### Two free fold-ins (do them in the Wave 0 PR, no-tech-debt rule)

4. **Adopt `time_to_verified_result` as the explicit decision metric** in the roadmap and persona docs. It is the north-star and the antidote to "fast model = cheaper": a 1000 tok/s model with 4 failed verify loops is slower AND costlier than Claude-right-once on the flat subscription. (Marlin pushes Mercury hard for SPEED; the agreed position is the verifier is what converts Mercury's speed into trustable shipped work, see section 4.)
5. **Extend `State` with LOGGED-ONLY fields** `assumptions_made`, `plan_contradictions`, `confidence` (richer escalation packets). HARD RULE: `confidence` is LOGGED, NEVER a gate input. We gate on reversibility/stakes, never on agent self-reported confidence (RLHF overconfidence: claimed 90% ~ 75% real). The GPT-5.5 spec gets this wrong; we do not.

**Wave 0 exit gate:** after the above, run one deliberately-ambiguous multi-iteration dogfood batch with a planted reward-hacking temptation + an injection probe, and confirm the stagnation brake, tamper tripwire, and injection fencing all fire. Nothing multi-model ships before this passes.

## 3. Design decisions already made (do NOT relitigate)

- Stagnation: progress = structured movement, not git churn; hard-stop + cheap notify, not a metered Proxy call.
- Ground-truth-to-Proxy: reconcile BEFORE the Proxy decides; the decision is a pure function of machine facts; Worker text is fenced UNTRUSTED in both proxies.
- The `ground_truth_summary` helper lives in `state.py` (shared by both proxies, DRY). Don't duplicate it.
- Confidence: logged, never gated.

## 4. Strategic context: the multi-model / Mercury decision (so you hold the line)

A long conversation evaluated a polished GPT-5.5 "multi-model orchestration" handover (Opus architect / Gemini senior / Mercury 2 ultra-fast swarm; model registry; provider adapters; research-claim harness). Verdict from a 3-lens senior panel: **validation, not redirection. ~60-80% of that spec is already in our code or already sequenced.** Decisions:

- **Do NOT build** the model registry, the three provider adapters, the ADR system, or the eval suite as standalone framework pieces. That is the founding doc's named #1 risk (scope creep into a general agent framework). Replace registry+adapters with a single config-driven `ExecutorProfile` dataclass (model_id + auth_mode + optional cost ceiling) that **defaults to Claude**. A registry is justified at provider #2 with a real consumer, not before.
- **Two hard gates on anything multi-model** (write into the roadmap, enforce):
  1. The Wave-2 held-out tamper-proof verifier must exist first (else the fast swarm / best-of-N just selects the best cheater).
  2. Every non-Anthropic provider key (Gemini, Mercury/Inception) routes through the **secrets proxy on ai-host** server-side, NEVER into a Worker transcript (those keys are already stripped as a contamination threat in `worker.py`).
- **Mercury reconciliation (Marlin's strong push for speed):** he is right that speed = time-to-market and metered cost is noise vs his time. The agreed nuance: Mercury's speed only converts to time-to-market if its output is trustable without manual review, which is what the held-out verifier provides. So: Mercury comes in EARLY for read-only reconnaissance (no verifier needed), and for code-WRITING / best-of-N only after the held-out verifier (Wave 2). Make it a one-line config flip via `ExecutorProfile`. Planner-deep / executor-fast split is correct.
- **Justification metric:** a second model gets adopted only on a measured `time_to_verified_result` win net of metered cost. "It's faster tok/s" is not a reason; "it lands verified work cheaper end-to-end" is.

## 5. Manual-mode skills layer (Wave 1, after Wave 0; do not start yet)

Marlin wants the SAME harness intelligence in manual terminal mode, not only the autonomous orchestrator. The plan:

- **One shared `playbook/` dir** vendored in this repo. Skills POINT at the canonical policy files (`personas/marlin.md` escalation policy, `personas/default.md` proxy policy, `goals/_template.md` + `verify.py` the verify contract, `state.py` schema, roadmap 4-tier autonomy table), NEVER re-prose them (re-prosing = drift, the #1 failure mode of this layer).
- **Exactly three new thin skills** (plus the existing `autonomous-orchestration`): `plan` (intake -> triage -> parallel read-only recon returning a fixed findings schema -> executable DAG of bounded leaf tasks written into `goals/<task-id>.md`), `feature` (bounded-build executor + dispatch bridge: one leaf, isolated worktree, SAME verify command as non-skippable definition-of-done, SAME structured result, SAME merge gate; can hand a parallel set of leaves to the orchestrator), `research` (THIN wrapper over the existing `deep-research` skill adding only claim/citation lineage; must not duplicate `deep-research` or `knowledge`).
- No triage skill, no router skill, no registry skill (triage is the `plan` skill's phase 1; routing is Wave-2/3 orchestrator config).
- Skills speak in ROLES (architect/senior/swarm/editor), never model names.

## 6. Hard constraints (every session must respect)

- Billing flat (subscription); secrets proxy for any non-Anthropic key; no scope-creep into a framework; no-tech-debt / fix-in-same-PR; production-grade not gate-passable.
- Typography: never em-dash or en-dash in anything you write. Expand acronyms on first use.
- Commit/push only when Marlin asks. The Wave 0 work is uncommitted on purpose (banked for one commit at the end). If asked to commit, end the message with the Co-Authored-By line.
- `uv run pytest` / `uv run ruff check` after every change; keep green.

## 7. Immediate next action

Finish Wave 0 items 1 and 2 (usage cap + tamper tripwire) plus fold-ins 4 and 5, keep all tests green + ruff clean, then run the dogfood exit gate. Present the whole branch for one commit when done.
