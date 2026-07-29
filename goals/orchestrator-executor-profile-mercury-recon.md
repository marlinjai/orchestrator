---
task: orchestrator-executor-profile-mercury-recon
verify: uv run pytest -q && uv run ruff check orchestrator/ tests/
auth_mode: subscription
# Targets the orchestrator repo itself (no separate spec file; this goal is the spec): high-stakes.
# Decision source: docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md (section 4)
# + knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 2: per-role model routing).
# Wave 2 / leaf L4.
---

# Goal

Build the Wave-2 "per-role model routing" seam as the smallest possible slice: a single
config-driven `ExecutorProfile` (model + auth + optional cost ceiling, DEFAULTING TO CLAUDE)
plus ONE non-Anthropic executor path, Mercury 2 (Inception) used ONLY for read-only
reconnaissance, with its API key routed server-side through the ai-host secrets proxy so it
NEVER enters a Worker transcript. Defaults are unchanged: with no profile configured, every
role runs Claude exactly as today (zero blast radius). This is the seam the rest of the
multi-model plan flips on, NOT a model registry and NOT provider adapters (those are the
roadmap's named #1 risk: scope creep into a general agent framework).

## Why this is allowed now (the two hard gates)

The multi-model line was gated behind two prerequisites; check both before relying on them:

1. **Held-out verifier exists + validated on a real repo.** DONE: the held-out gate (`held_out.py`,
   repo registry) is merged to master and fired live on `pin-to-clipboard`. This is why Mercury
   for read-only recon (no code written, no verifier needed) is unblocked, and why code-WRITING
   via Mercury stays out of THIS slice (it additionally needs a measured `time_to_verified_result`
   win and is best-of-N territory, a later goal).
2. **Non-Anthropic keys route through the secrets proxy, never into a transcript.** This slice MUST
   implement that, not assume it. `worker.py` already strips foreign provider keys from the SDK
   env as a contamination threat (`CROSS_PROVIDER_KEY_DENYLIST`); the Mercury key must reach the
   Inception API only via a server-side path on ai-host, and the orchestrator process must never
   hold the raw value.

## Read first

- `docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md` section 4 (the Mercury
  decision, verbatim: ExecutorProfile not registry; planner-deep/executor-fast; recon-early,
  write-after-verifier; the `time_to_verified_result` justification metric).
- `knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md` sections 4, 5 (Wave 2), 6
  (what NOT to build), 7 (control-plane layering).
- `orchestrator/worker.py`: `apply_env_contract`, `CROSS_PROVIDER_KEY_DENYLIST`, `build_worker_options`
  (how auth_mode + env scrubbing work today; the Mercury path must compose with this, not fight it).
- `orchestrator/config.py` + `orchestrator/orchestrator.py` (`OrchestratorConfig`, how run-start config
  threads through; mirror the `confirm_stakes`/`auth_mode` pattern for any new field).
- `skills/autonomous-orchestration/SKILL.md` (the secrets-proxy curl pattern: how a non-secret-leaking
  call gets its credential injected server-side via `execute_with_secrets` on ai-host) and CLAUDE.md
  point 1 (the secrets-proxy MCP is a safe default; Coolify-style secret-returning tools are not).

## Scope

1. **`ExecutorProfile` dataclass** (new, e.g. `orchestrator/executor.py`): `role` (e.g. `worker`,
   `recon`, `planner`), `model_id`, `auth_mode` (reuse the existing `AuthMode`), optional
   `cost_ceiling_usd`. A `resolve_executor(role) -> ExecutorProfile` that DEFAULTS every role to
   Claude (the current model) when nothing is configured. Config-driven from
   `~/.config/orchestrator/config.toml` (operator-owned, NOT goal frontmatter, NOT a per-repo
   registry field; same trust posture as the Marlin Proxy config). Speak in ROLES, never bake model
   names into call sites (the roadmap's "skills speak in roles" rule).
2. **Mercury recon executor** (read-only ONLY): a thin client that asks Mercury (Inception) a
   reconnaissance question and returns a STRUCTURED findings result (mirror the existing
   recon/findings shape if one exists; else a small typed dataclass). It runs NO tools, writes NO
   files, touches NO repo. The Inception API key is injected server-side on ai-host (secrets-proxy
   pattern), so the orchestrator process and any transcript only ever see the completion text, never
   the key. If the key/proxy is unavailable, FAIL LOUD and FALL BACK TO CLAUDE recon (never silently
   skip, never block the run).
3. **Wire one real call site**: the read-only reconnaissance role only (e.g. a pre-plan recon step,
   or expose `resolve_executor("recon")` where a recon call is made). Do NOT route the Worker
   (code-writing) or either Proxy through a non-Claude model in this slice. The Decision/Marlin
   Proxies stay Claude (they are the judges; their integrity is the whole trust model).
4. **`time_to_verified_result` hook**: record enough on `State`/usage to later compare a Mercury-recon
   run against a Claude-recon baseline (wall-clock + which executor served the role). Logged only;
   never a gate input. (Confidence/self-report stays logged-never-gated, consistent with Wave 0.)
5. **Secret scaffolding (structure only, Claude does NOT set real values)**: file an `open_thread`
   listing the exact Infisical key name to create as a PLACEHOLDER for the Mercury/Inception key and
   the path/project it belongs in, for Marlin to fill. Do not write a real key anywhere; do not print
   a key to logs.

## Definition of done

- `ExecutorProfile` + `resolve_executor` implemented; with NO config, every role resolves to Claude
  and all existing behavior is byte-for-byte unchanged (prove with a test).
- Mercury recon executor implemented behind the proxy-injected-key path; the orchestrator never holds
  the raw key; unavailable-key/proxy path falls back to Claude recon and is tested.
- The Worker, Decision Proxy, and Marlin Proxy still run Claude (assert no foreign model on the judge
  path).
- `uv run pytest -q` passes (add tests: default-to-Claude resolution; Mercury recon happy path with a
  mocked proxy client; fallback-to-Claude on missing key; judges stay Claude).
- `uv run ruff check orchestrator/ tests/` clean.
- ROADMAP.md "Shipped" updated with the slice (the existing entry format, no new columns).
- The autonomous-orchestration SKILL.md gains a short note: how per-role executors resolve, that
  defaults are Claude, that non-Anthropic keys go through the proxy, and that code-writing via a
  non-Claude model is NOT enabled by this slice.
- One conventional commit on the branch; `open_thread` filed for the placeholder Mercury key.

## Constraints

- DEFAULT TO CLAUDE everywhere. This slice ships dormant: nothing changes until an operator config
  explicitly points a role at Mercury. No regression to the single-model path.
- Do NOT build a model registry, provider adapters, an ADR system, or an eval framework (roadmap's
  named #1 risk). One `ExecutorProfile` dataclass, one recon client, one call site.
- Do NOT route the Worker or either Proxy through a non-Claude model. Recon is read-only and the only
  non-Claude surface in this slice.
- The Mercury/Inception key NEVER enters the orchestrator process env or any transcript: server-side
  injection on ai-host only. Compose with `apply_env_contract`'s existing foreign-key scrub.
- Subscription billing (flat); Claude stays the default so this adds zero metered cost until flipped.
- No em-dashes / en-dashes. Conventional-commit message. Stay in the worktree; do not push.

## Notes

- Architectural open question to resolve IN the slice (pick the simplest that keeps the key
  server-side): a Mercury completion is CONTENT, not a secret, so the `execute_with_secrets` MCP
  (which summarizes/redacts output via Ollama) is the WRONG transport for getting a usable completion
  back. Prefer a minimal forward path on ai-host that injects the key and returns the raw completion
  (e.g. a tiny curl-to-Inception run whose stdout is the completion, with only the key injected
  server-side), or run the recon client itself on ai-host. Document the choice in the commit.
- This is the Wave-2 "per-role model routing" item. It is the prerequisite seam for Wave-3 best-of-N
  and the planner-deep/executor-fast split, but does NOT implement either.
- Dispatch note (operator): the orchestrator's own repo is high-stakes; if it is registered at
  stakes_tier >= 3 in repos.toml, this run will need `--confirm-stakes` (Marlin's explicit go), by
  design.
