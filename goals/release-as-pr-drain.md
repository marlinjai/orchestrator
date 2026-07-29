---
task: release-as-pr-drain
verify: bats tests/release_drain.bats
# Verify is bats (bootstrap's harness). The new tests live in tests/release_drain.bats.
# Target repo (--project): ~/software-dev/marlinjai-bootstrap  (a new drain on drain-lib.sh)
# Wave 1 / leaf L6. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 1: "release-as-PR drain")
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L6)
# depends_on: [drain-lib-extraction]  (MERGED into rescue/orphan-skills)
shared_state: [drain]
---

# Goal

Add a **release-as-PR drain**: on a `completed` orchestrator run whose project repo has a git remote and
an unmerged `orchestrator/*` slice branch, open a version-bump DRAFT PR and send a Telegram nudge. It is a
thin caller on `drain-lib.sh` (from L1). It NEVER auto-publishes (`npm publish` is Tier-4, human-only) and
NEVER auto-merges (terminal action is a draft PR). It reuses the existing `/release` skill for the
repo-specific version-bump + changelog + PR, invoked headlessly with publishing disabled.

## Read first

- `modules/claude-marlin-extras/lib/drain-lib.sh` (L1, now merged): `drain_init`, `drain_acquire_lock`/`drain_release_lock`, `drain_log`, `drain_debounce_entry`, `drain_spawn_headless` (always sets the `CLAUDE_DRAIN_HEADLESS` sentinel). The drain MUST consume these, not re-duplicate.
- `modules/claude-marlin-extras/scripts/capture-drain.sh` (the proof-of-use caller pattern + the README skeleton) and `launchd/com.marlinjai.capture-drain.plist` (the timer shape).
- The `/release` skill (`~/.claude/skills/release/` or the bootstrap module that ships it): confirm it supports a no-publish / open-PR mode; if the flag name differs, use the skill's real flag. The drain MUST pass whatever makes it STOP BEFORE `npm publish`.
- `~/.orchestrator/tasks/<id>/state.json` shape: `status`, `repo_remote`, and the slice branch convention (`orchestrator/<task-id>`). This is how the drain finds a `completed` run to release.

## Scope

1. **`scripts/release-drain.sh`** (new, ~25-40 lines on `drain-lib.sh`): scan `~/.orchestrator/tasks/*/state.json`
   for runs with `status == completed`, a non-empty `repo_remote`, and an UNMERGED `orchestrator/<task-id>`
   branch in that repo (skip ones with no remote, e.g. closed-loop-sync). For each NOT-yet-released run
   (track released task-ids in a small state file, idempotent like the capture drain), `drain_spawn_headless`
   the `/release` skill in that repo on that branch in OPEN-PR / NO-PUBLISH mode, then a Telegram nudge.
   Honor a `RELEASE_DRAIN_DRY_RUN=1` that logs WOULD-release without invoking anything.
2. **`launchd/com.marlinjai.release-drain.plist`** (new): a timer (hourly is fine), mirroring the capture-drain plist env setup. Document the install step; do not auto-load it as part of the build.
3. **Telegram nudge**: reuse the existing secrets-proxy Telegram path the orchestrator/notify already uses (bot token + chat id injected server-side from Infisical, never in the process env). If a shared helper exists, call it; do not embed any token.
4. **Tests** (`tests/release_drain.bats`): mock `CLAUDE_BIN` + `gh` to tracing stubs; assert the drain (a) selects only `completed` + has-remote + unmerged-branch runs, (b) is idempotent (a second pass over an already-released run does nothing), (c) NEVER invokes a publish path, (d) `RELEASE_DRAIN_DRY_RUN=1` invokes nothing. Follow the `tests/drain_lib.bats` style; reuse `tests/helpers.bash`.

## Definition of done

- `scripts/release-drain.sh` is a thin `drain-lib.sh` caller (no duplicated lock/log/headless logic); the weekly/hourly plist exists + is documented (not auto-loaded).
- The drain opens a DRAFT PR via `/release` no-publish mode and never reaches `npm publish` or a merge.
- `bats tests/release_drain.bats` green: selection, idempotency, no-publish, dry-run all asserted.
- A short note in the `claude-marlin-extras` README: what the drain does, that it opens draft PRs and NEVER publishes/merges, and the install step.
- One conventional commit on the worktree branch.

## Constraints

- Stay in the worktree; do not push. NEVER `npm publish`, NEVER `gh pr merge`, NEVER push to a default branch. Terminal action is a DRAFT PR + a nudge.
- Consume `drain-lib.sh`; do not inline capture-drain's patterns (that is the tech debt L1 deleted).
- No token literals anywhere; Telegram goes through the existing server-side secrets-proxy path.
- No em-dashes / en-dashes (including in any generated PR text). Conventional-commit message.

## Notes

- depends_on L1 (`drain-lib-extraction`), MERGED into bootstrap `rescue/orphan-skills`, so `drain-lib.sh` exists.
- Skip runs with no remote (the drain is a no-op for local-only repos like closed-loop-sync). Skip runs whose branch is already merged or deleted.
- The version bump itself is `/release`'s job (repo-convention-aware: package.json vs pyproject vs Cargo). The drain only orchestrates WHEN to invoke it and enforces the no-publish ceiling.
