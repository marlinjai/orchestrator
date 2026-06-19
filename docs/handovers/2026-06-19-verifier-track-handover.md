---
type: handover
title: "Verifier track: brick 1 + 2 done (uncommitted), next = MCP enforcement + worktree isolation"
date: 2026-06-19
summary: >
  Resume point for the orchestrator held-out verifier track. Wave 0 is committed
  (7da7b6a). Brick 1 (operator repo registry) and brick 2 (held-out verifier
  runner) are DONE and GREEN but UNCOMMITTED on feat/wave-0-reliability-core. Two
  confirmed next bricks: enforce the registry's allowed_mcp_servers ceiling, and
  worktree-per-attempt isolation with proper cleanup.
tags: [orchestrator, verifier, held-out, repo-registry, mcp, worktree, handover]
projects: [orchestrator]
---

# Handover: verifier track (continue from brick 2)

Picking up an in-flight build. Read this, then continue. Do NOT redo brick 1 or
brick 2 (they exist in the working tree). Another session produced them; this
session and that one must not both touch the same files.

## 0. Orient first

- Roadmap (source of truth): `~/software-dev/knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md`
- Wave 0 resume point: `docs/handovers/2026-06-18-wave0-reliability-and-multimodel-handover.md`
- Repo guide: `CLAUDE.md` (architecture point 5 documents the trust anchor + held-out verifier)
- Operator playbook: `skills/autonomous-orchestration/SKILL.md` ("Repo registry" section)
- Tests: `uv run pytest -q` (NOT `pytest`; `python` is not on PATH, always `uv run`). Lint: `uv run ruff check orchestrator/ tests/`.

## 1. State of the tree (verify with `git -C ~/software-dev/orchestrator status`)

- Branch: **`feat/wave-0-reliability-core`**. Last commit: **7da7b6a** (Wave 0 reliability core).
- **338 tests pass, ruff clean.** No em-dashes / en-dashes anywhere (repo rule).
- **Brick 1 + brick 2 are UNCOMMITTED** (banked on the branch). FIRST ACTION: commit them as a green checkpoint before stacking more, so two sessions cannot clobber uncommitted work. Suggested message: `feat(verifier): operator repo registry + held-out verifier gate`.

Uncommitted files (this is the whole of brick 1 + 2; the 40-odd untracked `goals/*.md` are unrelated batch stubs, leave them OUT of the commit):

| File | What |
|---|---|
| `orchestrator/repo_registry.py` (new) | Brick 1. Operator-owned registry keyed by the REAL git remote (normalized `host/owner/repo`). Loads `~/.config/orchestrator/repos.toml` (override `ORCHESTRATOR_REPOS_CONFIG`). Fields: `held_out_verify`, `stakes_tier` (1-4), `allowed_mcp_servers`. Malformed = ValueError (fails the run loud). `resolve_repo_policy(project_dir)` returns a `RepoPolicy`. |
| `orchestrator/held_out.py` (new) | Brick 2. `decide_after_held_out(outcome, intree_verified=...)`: pass -> complete; fail -> escalate (reward-hack fingerprint when in-tree also passed); misconfigured -> escalate. Never a Worker retry. Execution reuses `verify.run_verify`. |
| `orchestrator/state.py` (mod) | `+repo_remote/held_out_verify/stakes_tier` (resolved policy), `+HeldOutRecord`/`last_held_out`, held-out + reward-hack line in `ground_truth_summary`. |
| `orchestrator/orchestrator.py` (mod) | Resolves the policy at run start (fails loud on bad registry); the stop branch now runs the held-out gate after the in-tree verify passes + tamper clears, OR as the sole gate when there is no in-tree verify. |
| `orchestrator/main.py` (mod) | `orchestrator status` surfaces `repo_remote`, `stakes_tier`, `held_out_verify`, `held_out_result`. |
| `docs/repos.example.toml` (new) | Commented example registry. Hidden-tests convention is `/opt/verifier-vault/<repo>/` (renamed from the vaguer `orchestrator-heldout`, Marlin's call). |
| `tests/test_repo_registry.py`, `tests/test_held_out.py` (new) + `test_orchestrator.py`, `test_state.py`, `test_wave0_exit_gate.py` (mod) | Coverage incl. real-git-repo integration (held-out fail escalates, sole-gate, malformed registry fails run). Test cfgs set `repos_config` to an absent tmp path so tests never read the real `~/.config/orchestrator/repos.toml`. |

`CLAUDE.md` + `SKILL.md` are updated to describe both bricks.

## 2. How the held-out verifier works (so you do not re-derive it)

The in-tree verify runs the goal's own tests in the Worker's tree, so a green
build is only as trustworthy as those tests. The held-out gate runs a SECOND,
operator-sourced test set the Worker cannot reach. Order on a stop-candidate:
in-tree verify passes -> tamper tripwire clears -> held-out gate runs. If the
in-tree suite is green but the held-out suite is red, that is the **reward-hack
fingerprint** and it escalates (recorded in `state.last_held_out`, surfaced in
`ground_truth_summary`). A held-out fail is NEVER fed back as a Worker retry
(that would teach to the hidden tests). The orchestrator only guarantees the
command is operator-sourced (registry, not goal file) and runs it; the filesystem
isolation (hidden tests on a path the Worker's user cannot write) is OPERATOR
setup, not enforced by the orchestrator.

This is the trust anchor the whole multi-model / Mercury plan is gated behind.

## 3. The two confirmed next bricks (Marlin approved both, 2026-06-19)

### Brick 3: enforce `allowed_mcp_servers` (the registry's last unused field)

Today `RepoPolicy.allowed_mcp_servers` is loaded + validated but NOT enforced.
Wire it as an operator CEILING on the Worker's MCP servers, keyed by the real git
remote (un-fakeable), in `orchestrator/worker.py`:

- Today a goal adds servers via `worker_mcp_servers` frontmatter, unioned onto the
  safe defaults through `WORKER_MCP_REGISTRY` (`load_worker_extras` /
  `build_worker_options`). That union has no per-repo operator ceiling.
- Change: when the resolved `RepoPolicy.allowed_mcp_servers` is set for the repo,
  the Worker's effective servers must be `safe_defaults UNION (goal_requested
  INTERSECT registry_ceiling)`. A goal can never enable a server the operator did
  not allow for that repo. When the registry field is `None`, keep current
  behavior (no extra ceiling), so existing repos are unaffected.
- Thread the resolved policy from `run_orchestrator` into `build_worker_options`
  (it is resolved at run start; pass it down rather than re-resolving).
- "A lot of MCP enforcement" (Marlin's words): be thorough. The safe defaults
  (`orchestrator-state`, `secrets-proxy`) must always survive; an unknown/typo
  server still drops with a warning; log the effective server set in run.log so
  it is auditable. Add tests: ceiling drops an out-of-ceiling goal server;
  `None` ceiling = unchanged; defaults always present.

### Brick 4: worktree-per-attempt isolation WITH proper cleanup (Wave 2)

Run each Worker attempt in its own git worktree so parallel/repeat attempts cannot
collide, and so a bad attempt is throwaway. Ship as N=1 collision-prevention
behind a flag with a fallback to the current in-place behavior (NOT "this makes
best-of-N safe", that needs more).

- The load-bearing trap (roadmap Wave 2): repoint cwd + reconcile + verify must
  happen ATOMICALLY against the new worktree, or you silently verify the wrong
  tree. `baseline_ref`, `reconcile`, the verify gate, the tamper scan, and the
  held-out gate all currently use `cfg.project_dir`; they must all follow the
  worktree consistently.
- Proper cleanup (Marlin emphasized this): after the attempt, tear the worktree
  down without losing work. See memory `orchestrator-worktree-merge-cleanup-order`
  and the SKILL.md "Auto-cleanup" section: `git worktree remove` only after the
  branch is merged/pruned; if it refuses because of unmerged or uncommitted
  changes, STOP and investigate, never `--force` blindly. An unchanged worktree
  auto-removes.
- Setup-online / work-offline split + `--ignore-scripts` (roadmap Wave 2) ships
  WITH the worktree because install is arbitrary code execution; you can stage it
  here or note it as brick 5.

## 4. Standing rules (do not violate)

- **Decide, don't ask** (Marlin, 2026-06-19): when you would ask a preference /
  design question, research it, recommend the best option, and proceed. Only the
  hard human gates still stop for Marlin: merge to main / revenue repos, prod
  deploy, real secret values, irreversible / external actions. Gate on
  reversibility + stakes, never on "feels like his call." See memory
  `decide-dont-ask-default`.
- **Hold the multi-model line:** no Mercury / provider-adapter / model-registry
  code yet. It stays gated on (a) this held-out verifier existing AND being
  validated on a real repo, and (b) non-Anthropic keys routing through the
  secrets proxy. Replace any "registry of models" urge with a single
  config-driven `ExecutorProfile` defaulting to Claude. Do NOT build a framework
  (the named #1 risk).
- **Operator-only setup that stays with Marlin:** where each repo's hidden tests
  physically live (the `/opt/verifier-vault/<repo>/` dir, different-owner /
  read-only) and which repos are high-stakes (`stakes_tier`). Do NOT author real
  hidden-test content autonomously; that is his trust-root.
- Billing flat (subscription). No em-dashes / en-dashes. Conventional commits.
  Commit only when asked. `uv run pytest` + `uv run ruff check` green after each
  change.

## 5. After bricks 3 + 4

The payoff Marlin is waiting for: stand up a real `/opt/verifier-vault/<repo>/`
for ONE repo (his 5-minute setup) and dogfood the held-out verifier end-to-end,
planting a regression to confirm the fingerprint fires on real work. Then, and
only then, the Mercury read-only-recon entry point becomes unblocked.
