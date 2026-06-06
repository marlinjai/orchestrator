---
name: autonomous-orchestration
description: Run a task autonomously via the orchestrator CLI, a Python Worker + Decision Proxy loop that takes a goal file and runs to completion without further human turns. Use when the user says "autonomous", "autonomous orchestration", "run autonomously", "dispatch a worker", "kick this off in the background", "launch a parallel batch", "fire this off while I work on something else", "implement this spec on its own", "run the orchestrator", or "have an agent land this end-to-end". Also use when the user references their `~/software-dev/orchestrator` repo, mentions "worker + proxy", "Marlin Proxy", "shadow mode", "layered autonomy", or asks about `state.json`, `task-id`, kill switch, escalation, reconciliation, or `marlin-proxy review`. Do NOT use when editing the orchestrator's own source code, brainstorming features, doing interactive coding, reviewing a Worker's output, or answering architecture questions about the orchestrator itself (those belong to the repo's CLAUDE.md). This skill is the operator's playbook for driving the CLI from outside, not a re-implementation of it.
---

# Autonomous orchestration

The orchestrator is an autonomous Claude Code runner: it spawns a Worker (Claude Code SDK session) on a goal file, polls the transcript between iterations, and feeds each iteration to a stateless Decision Proxy LLM that returns `continue | replan | escalate | stop`. State lives at `~/.orchestrator/tasks/<task-id>/`.

When the Decision Proxy returns `escalate` and the **Marlin Proxy** is enabled, a second persona-driven LLM call decides whether Marlin would auto-approve, defer, or genuinely needs to be interrupted. This is the layered-autonomy feature: it removes the mechanical back-and-forth (merge-after-verify, branch cleanup, status, procedural questions) while still escalating taste, scope, product, and irreversible-ops decisions. See "Marlin Proxy" below. It defaults to OFF.

You are NOT the orchestrator. You operate it from the outside via shell commands.

## When to use

Use this skill when:
- The user says "autonomous", "run autonomously", "dispatch", "fire this off", "kick off in the background", "have an agent land this", "launch a batch", "in parallel" applied to a coding task
- The task is well-specified: a spec file, a goal markdown, or at least a clear definition of done
- The user wants the work done without further interactive turns
- Multiple independent tasks can run in parallel (one Worker per worktree)
- The user references the orchestrator repo, asks about state.json/task-id/escalation/reconciliation, or is troubleshooting a running Worker

## When NOT to use

Don't invoke this skill for:
- **Editing the orchestrator's own source code** (you're a normal Claude Code session; act normally, use the repo's CLAUDE.md)
- **Brainstorming** what to build, scoping a feature, exploring options (use interactive Claude Code; the orchestrator can't talk back during a run)
- **Code review** of a Worker's output (review is a separate, interactive activity)
- **Architecture questions** about how the orchestrator itself is implemented (CLAUDE.md in the repo is the canonical source)
- **Tasks needing repeated human decisions** mid-flight (the Worker will hit `escalate` or stall)
- **Interactive coding** where the user is iterating turn-by-turn with you

## Install (one-time per machine)

```bash
uv tool install git+https://github.com/marlinjai/orchestrator
# or, for local development install:
cd ~/software-dev/orchestrator && uv tool install --editable .
```

After install, the `orchestrator` binary is on PATH everywhere.

## Version check (run this before every dispatch)

The minimum required version is **0.3.0** (adds Layer 3 context-handover). Before dispatching any task, verify and auto-upgrade if needed:

```bash
INSTALLED=$(uv tool list 2>/dev/null | grep claude-code-orchestrator | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "0.0.0")
MIN="0.3.0"
if [ "$(printf '%s\n' "$MIN" "$INSTALLED" | sort -V | head -n1)" != "$MIN" ]; then
  echo "orchestrator $INSTALLED < $MIN, upgrading..."
  uv tool upgrade claude-code-orchestrator
  uv tool list | grep claude-code-orchestrator
fi
```

If `orchestrator` is not found at all, run the one-time install above first. The bootstrap (`marlinjai/bootstrap --profile marlin-dev`) handles this automatically on new machines via the `orchestrator-cli` module.

## The canonical flow

1. **Write a goal file** at `~/software-dev/orchestrator/goals/<task-id>.md`. Use `goals/_template.md` as the starting shape. The goal file is the Worker's full instruction set: definition-of-done, constraints, what NOT to touch.

2. **Set up a worktree** in the target repo (one worktree per task isolates state):
   ```bash
   cd <target-repo>
   git worktree add -b orchestrator/<task-id> ../<repo>-orch-<task-id> main
   cd ../<repo>-orch-<task-id> && <install command if any>  # e.g. pnpm install
   ```

3. **Launch detached** so the Worker survives the shell:
   ```bash
   cd ~/software-dev/orchestrator
   nohup orchestrator start \
     --goal goals/<task-id>.md \
     --project <worktree-path> \
     --task-id <task-id> \
     --max-iterations 30 \
     --max-hours 1.0 \
     > /tmp/orch-<task-id>.log 2>&1 &
   ```

4. **Monitor** by polling `state.json` or via `orchestrator status --task-id <id>`. Terminal states are `completed | escalated | stopped | failed`.

5. **Auto-review, push, PR, merge** without operator-side user gates (per Marlin's standing rule for orchestrator-driven slices):

   a. **Auto-review the diff** in the worktree: confirm acceptance criteria from the spec, spot-check key signature changes, verify no scope creep beyond what is justified. If the Worker filed legitimate open threads for pre-existing issues, fix the tiny ones in-place (per Marlin's "no open follow-ups, no tech debt" rule) as additional commits on the same branch.

   b. **Run final verification** before push: `pnpm build`, package tests, `tsc --noEmit`. If the repo's build needs Infisical-injected env vars (common: `DATABASE_URL` for Prisma at build time), run `infisical run -- pnpm build` to confirm green. Bare-build failures from missing env are NOT regressions — they reflect the repo's existing `infisical run` wrapping pattern.

   c. **Push the branch**: `git push -u origin <branch>`. Never push to `main` directly.

   d. **Open the PR** via `gh pr create --base main --head <branch>`. PR description should summarize what changed, what's verified, and any out-of-scope items filed as follow-ups.

   e. **Auto-review the PR**: wait for CI (`gh pr checks <num>`), confirm `mergeStateStatus: CLEAN` and `mergeable: MERGEABLE` via `gh pr view <num> --json mergeable,mergeStateStatus,statusCheckRollup`. If only a security scan is configured (no test workflow), local verification from step (b) is the gate.

   f. **Merge**: `gh pr merge <num> --squash --delete-branch` (squash matches Marlin's repos' convention; PR-number suffix on main commits is the tell). For non-team PR authors, follow the bridge-commit rule from [[feedback_always_bridge_non_team_prs]] if applicable.

   g. **Clean up** (non-skippable, see "Auto-cleanup" below): in the primary repo, `git fetch --prune`, `git checkout main`, `git pull`, then `git worktree remove ../<repo>-orch-<task-id>` and `git branch -D orchestrator/<task-id>` (or the slice's actual branch name). If the worktree refuses to remove because it has unmerged changes, STOP and investigate. Do not `--force` blindly.

   h. **Proceed to the next slice** without user input. The operator (you) is trusted to gate + merge orchestrator-driven slices end-to-end. Stop and ask only if: tests fail in CI, the Worker escalated, the diff reveals scope creep that wasn't justifiable, or the change has cross-repo ripple beyond the current spec.

   See [[feedback_orchestrator_auto_merge]] memory for the standing rule. This replaces the older "cherry-pick + push manually" pattern; do NOT cherry-pick when a worktree exists.

## Batch dispatch (dependency-aware)

For chains of related tasks (slice 1 then slice 2 then slice 3, or two parallel-safe tasks that both touch `prisma`), declare dependencies in each goal file's frontmatter. The skill operator computes the dep graph from frontmatter directly. Never maintain a separate dispatch-plan file alongside the goal frontmatter: two sources of truth drift.

### Frontmatter fields

Extend each `goals/<task-id>.md` frontmatter with optional declarations:

```yaml
---
task: <task-id>
spec: <path/to/spec.md>
depends_on: [<other-task-id>, ...]   # must MERGE before this task launches
shared_state: [<tag>, ...]           # serializes with any task sharing a tag
verify: pnpm test && pnpm build && tsc --noEmit && pnpm lint   # gate before accepting `completed`
verify_fix_cap: 2                    # consecutive verify failures tolerated, then escalate
verify_timeout_s: 1200               # per-run wall-clock timeout (default 1200 = 20 min)
---
```

`depends_on` and `shared_state` are optional. Absent both, the task is parallel-safe (an independent unit).

`verify` is the in-loop completion gate (orchestrator source, not the operator's job): before the orchestrator accepts the Worker's `stop` as `completed`, it runs this command in the worktree. Pass goes to `completed`; a failure is fed back to the Worker for up to `verify_fix_cap` retries (default 2) then escalates; a denylisted command or a timeout escalates immediately. Omit `verify` and completion is NOT build-verified (the run logs a warning, and the operator's manual `pnpm test && pnpm build` stays mandatory). The gate runs a shell command and reads the exit code, so a project-specific critic (e.g. a values-only schema round-trip) is just appended to the command: `... && pnpm verify:schema-roundtrip`.

`depends_on` is for explicit ordering: slice 3 cannot start until slice 2's PR has merged into the base branch.

`shared_state` is for implicit collisions: two tasks that both touch `pnpm-lock.yaml` will conflict at merge time even if neither knows about the other. Declaring the tag forces sequential dispatch.

### shared_state canonical vocabulary

Use these tags before inventing new ones. The set grows on demand: add a new tag only when a real slice needs one, then document it here in the same PR.

| Tag           | Covers                                                                  |
|---------------|-------------------------------------------------------------------------|
| `lockfile`    | `pnpm-lock.yaml`, `package-lock.json`, `uv.lock`, `Cargo.lock`, etc.    |
| `prisma`      | `prisma/schema.prisma` edits                                            |
| `migrations`  | Adds or edits any DB migration file (Prisma, SQL, Drizzle, Alembic)     |
| `env`         | Renames or adds env-var references the runtime depends on               |
| `workspace`   | `pnpm-workspace.yaml`, root `package.json`, monorepo topology           |
| `next-config` | `next.config.ts` or framework root config                               |
| `claude-md`   | The repo's `CLAUDE.md`                                                  |

Two tasks declaring any overlapping tag MUST run sequentially. Reason: merge conflicts on lockfile / schema / topology files are guaranteed and hand-merging is the slow path.

### Dispatcher loop

For a batch goal-file glob (e.g. `goals/lumitra-*.md`):

1. **Parse all frontmatter** in the batch. Build a directed dep graph from `depends_on`. Annotate each node with its `shared_state` tags.
2. **Stale-worktree prune (pre-flight)**: in the target repo, `git worktree list --porcelain`. For each worktree on a branch matching `orchestrator/*` OR `feat/*-orch-*` (or your slice-branch convention) whose task-id is in a terminal state (`completed | failed | stopped` per `~/.orchestrator/tasks/<id>/state.json`) AND whose branch is merged or deleted upstream: `git worktree remove` + `git branch -D`. Recovers from any prior batch that died mid-run.
3. **Compute the next launchable set**: tasks where every `depends_on` entry is in a merged state AND no currently-running task shares any `shared_state` tag.
4. **Dispatch the set** using step 2 to 4 of "The canonical flow": one worktree per task, `nohup orchestrator start ... &` per task.
5. **Wait for at least one terminal state**. Poll `state.json` for the running set (or `orchestrator status` per task).
6. **Per terminal task**: apply the auto-review-push-PR-merge flow from step 5(a) to 5(g). On successful merge, the task becomes a dep-satisfier for downstream tasks.
7. **Loop back to step 3** until the dep graph is exhausted, OR any task ends in `failed` / `escalated`. In that case, stop the loop, surface the failure, do NOT auto-dispatch dependents.
8. **Final sweep**: any remaining `orchestrator/*` worktrees + branches in the target repo whose tasks reached terminal-completed state and are merged get removed.

### When NOT to bother with dep declarations

One-off slices that nobody is chaining. Just dispatch one Worker via the per-task flow. The dep machinery only earns the frontmatter ceremony when two or more related tasks are in flight (or about to be).

## Auto-cleanup (non-skippable)

Three integration points, all owned by the skill operator (you), not the orchestrator process:

1. **After successful merge** in step 5(g) of the canonical flow: `git worktree remove ../<repo>-orch-<task-id>` and `git branch -D <branch>` for the local slice branch. This is required, not optional. Worktrees accumulate fast and `git worktree list` becomes unreadable within a week of active batches.
2. **Pre-flight** at batch start: see step 2 of the dispatcher loop above.
3. **Final sweep** at batch end: see step 8 above. The task's state directory at `~/.orchestrator/tasks/<task-id>/` is kept by default (useful postmortem trail). Remove only if you explicitly need a clean slate.

If a worktree won't remove because it has uncommitted work, STOP. That work is either (a) the merged PR's diff that didn't get pruned by `git fetch --prune` (run `git fetch --prune` and retry), or (b) something else (a manual edit you forgot about). Investigate, never `--force` blindly.

## Marlin Proxy (layered autonomy)

The Marlin Proxy sits on the Decision Proxy's `escalate` path. When the Decision Proxy decides Marlin is needed, the Marlin Proxy (a stateless single-shot call using `personas/marlin.md`) classifies the escalation into a category and returns `auto_approve | auto_defer | escalate`. It removes the mechanical ~70% of operator back-and-forth while keeping the taste/scope/product/irreversible ~30% in Marlin's hands.

**It defaults to OFF.** Nothing auto-decides until you enable it. The whole feature is reversible in seconds.

### Enabling it (config)

Create `~/.config/orchestrator/config.toml`:

```toml
[marlin_proxy]
mode = "shadow"   # off | shadow | live

[marlin_proxy.categories]
merge_after_verify  = "live"
branch_cleanup      = "live"
status_fetch        = "live"
procedural_workflow = "shadow"
scope_change        = "escalate"
product_decision    = "escalate"
risk_tradeoff       = "escalate"
irreversible_ops    = "escalate"   # hard-wired; cannot be relaxed
context_saturation  = "shadow"
unknown             = "escalate"

[marlin_proxy.thresholds]
context_handover_tokens   = 80000   # auto-handover trigger (~50% of 200k window)
context_saturation_tokens = 120000  # hard escalation fallback if handover fails
per_decision_timeout_ms   = 30000
```

Per-category mode: `live` (proxy decides), `shadow` (proxy decides but still escalates, logging its would-be choice for review), `escalate` (always interrupt Marlin). The global `mode` is a ceiling: global `shadow` downgrades every `live` category to `shadow`; global `off` escalates everything.

Per-task override in the goal-file frontmatter:

```yaml
---
task: clean-up-worktrees
marlin_proxy: live
marlin_proxy_categories:
  branch_cleanup: live
---
```

### Rollout (the safe path)

1. **off** (default): no behavior change.
2. **shadow** (1 to 2 weeks): proxy decides on every escalation but still interrupts Marlin. Every would-be decision is logged. Collect agreement data.
3. **live on safe categories**: flip `merge_after_verify`, `branch_cleanup`, `status_fetch` to `live`. Keep taste categories on `escalate` forever.
4. Expand only categories whose shadow agreement is >95% over 20+ decisions.

### Operating it

- **Review**: `orchestrator marlin-proxy review` prints agreement-by-category and recent disagreements from the ledger.
- **Ledger**: append-only JSONL at `~/.orchestrator/marlin-proxy-decisions.jsonl`; human-readable lab notes at `~/.orchestrator/marlin-proxy-notes.md`.
- **Kill switch**: `touch ~/.orchestrator/marlin-proxy.disabled` forces every decision to escalate on the next decision boundary, regardless of config. Remove the file to resume. This is independent of the per-task `STOP` kill switch (which halts the whole run).
- **Autonomy stats**: `orchestrator status --task-id <id>` shows `approved / deferred / escalated` counts, max streak, and autonomous runtime.

### Fail-safe guarantees

Malformed persona output, a bad/missing choice, or a per-decision timeout all resolve to `escalate`, never a silent auto-approve. A missing persona file forces `mode=off`. `irreversible_ops` (prod deploys, secret rotation, DNS, destructive migrations) is hard-wired to escalate and cannot be relaxed by config or per-task frontmatter.

## Authentication (critical)

**The Worker uses the user's Claude Code login subscription by default**, not API billing. The orchestrator strips `ANTHROPIC_API_KEY` from its own env before spawning the SDK subprocess (see `orchestrator/worker.py::_scrub_anthropic_api_key`).

This means:
- Wrapping the launcher in `infisical run --env=dev --path=/ --` is **safe** for injecting secrets the *downstream app* needs at runtime. The scrub keeps the Worker on subscription.
- The Worker writes code that references `process.env.ANTHROPIC_API_KEY` for the *app's* use; the key only needs to exist at app-run time (e.g. when the user later runs `pnpm dev`), not at orchestrator-spawn time.
- Never set `ANTHROPIC_API_KEY` in your shell rc files thinking it'll "help" the orchestrator. It will silently switch the Worker to direct API billing on that key.

## State directory layout

```
~/.orchestrator/tasks/<task-id>/
  state.json    # pydantic-validated, atomically written
  run.log       # tee'd Worker stdout/stderr
  STOP          # touch to halt at next iteration boundary
```

Key state.json fields (v0.3+):
- `status`: running | completed | escalated | stopped | failed
- `iteration`, `max_iterations`
- `baseline_ref`: git HEAD of project at orchestrator start
- `commits[]`: each entry has `sha`, `message`, `decided_by` (proxy = Worker self-reported via update_state; system = orchestrator detected via git reconcile)
- `files_touched[]`: same provenance model
- `usage[]`: per-iteration `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`, `worker_ms`, `proxy_ms`
- `handovers[]`: each entry has `at_turn`, `reason`, and `doc` (path to HANDOVER.md). Populated when context crosses `context_handover_tokens` and the Worker produces a git-verified checkpoint. A non-empty list means the run survived multiple session legs.
- `autonomy_stats`: Marlin Proxy counters: `auto_approved`, `auto_deferred`, `escalated`, `decisions_between_escalations`, `max_decisions_between_escalations`, `autonomous_runtime_ms`
- `exit_reason`: terminal explanation string

## Things to confirm with the user before dispatching

- Which target repo / worktree path
- What spec or goal-file content (or, if creating one, what definition of done)
- `max_iterations` and `max_hours` (defaults: 50 / 4h; smaller is safer for first runs)
- For multi-task batches: do any tasks share `depends_on` or `shared_state` declarations? If so, dispatch via the "Batch dispatch" loop, not a hand-rolled `for` loop.
- Whether ANTHROPIC_API_KEY needs to be injected at app-run time separately (different scope from the orchestrator launch)

## Red flags during a run

- `commits[*].decided_by` shows `system` entries → Worker isn't calling `update_state(kind="commit")` reliably. Functional, but state is one-sided. Worth noting in v2 retro.
- `usage` shows monotonically growing input_tokens with no cache_read → caching broken, will blow rate limits on multi-iteration runs.
- `iteration` climbing without commits/files growth → stagnation streak. Will eventually escalate (Theme 4 detection lands in a later slice).
- `exit_reason` containing "Credit balance is too low" → `ANTHROPIC_API_KEY` leaked into orchestrator env despite the scrub (or the scrub regressed). Check `worker.py`.

## Where the source lives

- Code: `~/software-dev/orchestrator/`
- Plans: `~/software-dev/orchestrator/docs/plans/`
- CLAUDE.md: `~/software-dev/orchestrator/CLAUDE.md` (architecture + SDK gotchas)
- v2 first slice plan: `docs/plans/2026-05-24-orchestrator-v2-first-slice.md`
- Marlin Proxy plan: `docs/plans/2026-05-27-marlin-proxy.md`
- Marlin Proxy code: `config.py`, `ledger.py`, `marlin_proxy.py`, persona at `personas/marlin.md`
