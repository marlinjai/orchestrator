---
task: arbosano-phase-5-publish-merge
spec: plans/2026-05-30-phase-5-publish-pipeline.md
marlin_proxy: shadow
---

# Goal

Implement arbosano content-as-code **Phase 5.3 to 5.6**: the adversarial Claude reviewer, the path-scoped imperative auto-merge with the `PUBLISH_AUTONOMY` ladder, the `MERGE_TOKEN` deploy-fire wiring, and the audit stub. PLUS **Step 0** (a hard prerequisite): widen `src/lib/zones.ts` `BLOCKED_GLOBS` to cover the admin machinery, and retire the inline YAML classify mirror in `publish-gate.yml` by importing `zones.ts` directly. You run inside a git worktree on branch `feat/phase-5-publish-merge` off `main`. Build to green **with `PUBLISH_AUTONOMY` defaulting to `shadow` (nothing auto-merges)**, unit-test the classify + merge-decision logic, and do NOT push, open a PR, merge, or deploy. The operator reviews + opens the PR.

The authoritative spec is `plans/2026-05-30-phase-5-publish-pipeline.md` (read 5.3 to 5.6 fully). Cross-phase contracts: `plans/2026-05-30-content-as-code-roadmap-phases-2-5.md`. The hosted-/admin security context that makes Step 0 urgent: `plans/2026-05-31-phase-2-5-hosted-admin-executor.md`.

## Repo-state precondition

- Branch `feat/phase-5-publish-merge` in a worktree off `main` (HEAD `1fdbded`). Clean tree at start or escalate.
- **Phase 5.0 to 5.2 ALREADY SHIPPED.** `.github/workflows/publish-gate.yml` already runs `classify` (dorny/paths-filter, the inline glob mirror you will retire), `lint`, `typecheck`, `fences` (`pnpm test`), `build`, `dash-guard`, and `visual-diff`. REUSE and EXTEND this file; do NOT recreate it or duplicate jobs.
- `picomatch` is ALREADY a dependency (Phase 2 `tools.ts` uses it). `node --experimental-strip-types` + the `scripts/tools-loader.mjs` import pattern is ALREADY how `.mts` fixtures import `.ts` modules (see `src/lib/admin/__tests__/tools.fence.test.mts`). Use these; add NO new dependency.
- Reuse, never recreate: `src/lib/zones.ts` (`ZONE_POLICY`, the glob arrays), `src/lib/admin/tools.ts` (`AGENT_MACHINERY_GLOBS` + the picomatch parens-escaping note at the `src/app/\\(admin\\)/**` glob), `src/lib/media.ts` (`COMMITTED_MEDIA_MAX_BYTES`, exported-but-unused today).

## Decisions already taken (do NOT re-litigate; list them in your final report)

- **Reviewer talks to the Anthropic API via raw `fetch`** (no `@anthropic-ai/sdk` dependency: this keeps the gate honest and the branch lockfile-clean so it merges independently of Phase 4). Prompt-cache the system prompt via the `cache_control` block on the system message.
- **`PUBLISH_AUTONOMY` defaults to `shadow`.** Shadow = comment "READY TO MERGE" + a label, and DO NOT merge. `scoped` = auto-merge content/media only. `wide` = content/media AND components. Graduating is a one-line `gh variable set`. NEVER use `gh pr merge --auto` (branch protection is 403 on the free private repo; this job IS the gate).
- **The merge step authenticates with `MERGE_TOKEN`** (a GitHub App installation token, Marlin's secret), NEVER `GITHUB_TOKEN` (the recursion guard would silently suppress `deploy.yml` and content would never ship). Since shadow does not merge, this is wired-but-dormant; document the trap in a comment.
- **Step 0 zones globs** (escape the route-group parens for picomatch exactly as `tools.ts` does): add to `BLOCKED_GLOBS`: `src/lib/admin/**`, `src/lib/worktree-sessions/**`, `src/app/api/admin/**`, `src/app/\\(admin\\)/**`. This is the documented pre-auto-merge prerequisite (the `tools.ts` NOTE at the `AGENT_MACHINERY_GLOBS` comment). Keep `AGENT_MACHINERY_GLOBS` in `tools.ts` as defense-in-depth, but update its stale NOTE to say `zones.ts` now classifies these as blocked.
- The 2-of-3 reviewer lens matrix (ux, code, policy) applies to `components`; a single lens (solo) to `content`/`media`. A reviewer `block`, or `classify.blocked == true`, or any red deterministic job, all force `needs-human` and never merge, in EVERY rung.

## Build

### Step 0: zones hardening + retire the YAML classify mirror (do FIRST, it is the foundation)
1. Widen `BLOCKED_GLOBS` in `src/lib/zones.ts` with the four admin-machinery globs above. Confirm the existing four-fence fixture (`pnpm test`) STILL PASSES: admin-machinery writes are now caught by `blockedMatch` before `machineryMatch`, both return `fence1-glob`, so the `assertErr(..., "fence1-glob")` assertions hold. If any assertion would need weakening, escalate.
2. Update the stale NOTE comment in `tools.ts` (do not remove `AGENT_MACHINERY_GLOBS`; it stays as defense-in-depth).
3. Retire the inline glob mirror: add `.github/reviewer/classify.mjs` (or similar) that imports `ZONE_POLICY` from `src/lib/zones.ts` (via `node --experimental-strip-types` + the tools-loader pattern), takes the PR's changed-file list (from `git diff --name-only <base>..<head>`), classifies most-restrictive-wins, and prints `content`/`components`/`blocked` outputs for the workflow. Replace the `dorny/paths-filter` step's inline `filters:` with a call to this script so `zones.ts` is the SINGLE source of truth. The audit verified the inline globs are byte-exact to `zones.ts` today, so this must not change any classification (unit-test that).

### 5.3 adversarial reviewer (`.github/reviewer/run.mjs`)
A Node script run in a reviewer job that runs ONLY after the deterministic jobs pass and `classify.blocked != 'true'`. Inputs: the PR diff + the structured PR body + the rendered screenshots, NOT the authoring chat transcript (independence). Refute-stance prompt. Strict JSON verdict `{verdict:"block"|"pass", confidence, blocking_reasons, notes}`. Components -> a 3-lens matrix (ux/code/policy); content/media -> solo. `ANTHROPIC_API_KEY` from a GH secret, server-side, prompt-cached system prompt, NEVER echoed to logs.

### 5.4 path-scoped imperative auto-merge (`.github/reviewer/decide-and-merge.mjs` + the `auto-merge-decision` job)
`needs` all prior jobs, `if: always()`, `contents:write + pull-requests:write`. Fail-closed order: (1) any deterministic job `!= success` -> `::error::` + exit (nothing merges on red); (2) `classify.blocked == true` -> `needs-human` label + comment + stop, EVERY rung; (3) tally verdicts (content: 1 pass; components: >=2 of 3; any block -> needs-human) AND read `PUBLISH_AUTONOMY`: `shadow` -> comment + label, NO merge; `scoped` -> merge content/media; `wide` -> + components. Merge = `gh pr merge <n> --squash --delete-branch` authenticated with `MERGE_TOKEN`. NEVER `--auto`.

### 5.5 the deploy-fire trap + 5.6 audit stub
Document (comment) that the merge uses `MERGE_TOKEN` so `deploy.yml`'s `on: push: main` actually fires (the `GITHUB_TOKEN` recursion guard would silently no-deploy). `deploy.yml` needs NO structural change. Ship a `writeAuditRow()` NO-OP stub in `decide-and-merge.mjs` with a clear Phase-4 wiring comment (it will call the Phase 4 `recordAudit`).

### Fold-in: the deferred Phase 3.5 deterministic gate lints (same `publish-gate.yml`, cohesive)
Add three deterministic checks to the gate (they are small and belong here, per the handover): (a) **media-lint**: every ADDED `public/media/` file matches `^[0-9a-f]{8}\.webp$`; (b) **committed-media max-bytes**: wire `COMMITTED_MEDIA_MAX_BYTES` from `src/lib/media.ts` (currently exported-but-unused) to fail if an added committed media file exceeds it; (c) **empty-alt structural lint**: fail on an added image reference with an empty/missing alt. If folding these in pushes the change past a reviewable size, do (a)+(b)+(c) only if the reviewer + merge are already green; otherwise file them as an `open_thread` and escalate the scope.

## Definition of done

- `pnpm exec eslint --max-warnings=0 .`, `pnpm exec tsc --noEmit`, `pnpm build` (dummy env) all pass.
- `pnpm test` (the four-fence fixture + the runner argv test) STILL passes after the `zones.ts` change.
- A unit test for `classify.mjs`: a `src/content/**`-only diff -> `content`; a `next.config.ts` diff -> `blocked`; a `src/lib/admin/auth.ts` diff -> `blocked` (the NEW behavior from Step 0); a `src/components/**` diff -> `components`. Assert it matches what the old inline globs produced (no classification drift) for a representative set.
- A unit test for the `decide-and-merge` tally: content 1-pass -> merge-eligible at `scoped`; components needs 2/3; any reviewer `block` -> `needs-human`; `classify.blocked` -> `needs-human`; any red deterministic job -> no merge; `shadow` -> NEVER merges regardless of verdict.
- `grep -rnP '[\x{2013}\x{2014}]'` finds no dashes in any added file. The reviewer script never prints `ANTHROPIC_API_KEY` (grep the script).
- `PUBLISH_AUTONOMY` documented as defaulting to `shadow`; the repo-variable read is present.
- `update_state(kind="commit"/"file_touched"/"decision")` as you go; `kind="open_thread"` for: (1) Marlin creating the `ANTHROPIC_API_KEY` GH secret (reviewer), (2) Marlin creating the `MERGE_TOKEN` GitHub App + secret + the GitHub Team decision, (3) the operator running a live reviewer call + a hand-opened-PR shadow dry-run to calibrate before graduating `PUBLISH_AUTONOMY`, (4) wiring `writeAuditRow()` to Phase 4 `recordAudit` once Phase 4 merges.
- Final message: decisions taken, files added (confirm NO new deps), the fail-closed invariants you proved by unit test, the open threads, and confirmation lint + tsc + build + `pnpm test` + the new unit tests are green.

## Constraints

- Stay inside this worktree. No file outside it. Do NOT push, open a PR, merge, or deploy.
- **Add NO new dependency** (the reviewer uses raw `fetch`; classify uses the existing `picomatch` + `node --experimental-strip-types`). A new dep is an escalation, not a decision.
- The auto-merge job MUST fail closed: a red deterministic job, a `blocked` classification, a reviewer `block`, or `shadow` autonomy each prevent merge. If you cannot make this honest, escalate (do not ship a weak gate; this is the autonomous merge actor).
- No em-dashes (U+2014) or en-dashes (U+2013) anywhere.
- `ANTHROPIC_API_KEY` + `MERGE_TOKEN` are referenced as GH secrets only: never hardcoded, never echoed to logs, never in the browser.
- Do NOT touch `deploy.yml` structurally (it already deploys on push:main; the merge re-triggers it via `MERGE_TOKEN`).
- Expected footprint: edits to `zones.ts` + `tools.ts` (NOTE only) + `publish-gate.yml`, plus `.github/reviewer/*.mjs` + unit tests. No new deps. Material scope beyond that is an escalation.

## Escalation rules

- Clean-tree precondition fails: escalate.
- The `zones.ts` change forces a fence-fixture assertion to be weakened to pass: escalate (do not weaken a fence).
- The fail-closed merge gate cannot be made honest with the workflow `if:`/`needs` chain alone: escalate.
- You would need a new dependency, or to touch a `BLOCKED_GLOBS` file beyond `publish-gate.yml` + `.github/reviewer/**`: escalate.
- The installed Anthropic HTTP API shape (messages endpoint, cache_control) is ambiguous and you would guess: escalate.

## Out of scope (stated, not parked)

- Creating the `ANTHROPIC_API_KEY` + `MERGE_TOKEN` GH secrets, the GitHub App, the GitHub Team upgrade: Marlin's by-hand steps (open_threads).
- Graduating `PUBLISH_AUTONOMY` past `shadow`: Marlin's call after calibration.
- The live reviewer integration test + the shadow dry-run on a hand-opened PR: operator verification (open_thread).
- Wiring `writeAuditRow()` to the real Phase 4 `recordAudit`: lands when Phase 4 merges (open_thread).
- Any push, PR, merge, or deploy.
