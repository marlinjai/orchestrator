---
task: arbosano-visual-diff-admin-exhibit
verify: pnpm install --frozen-lockfile && pnpm exec tsc --noEmit && pnpm exec eslint --max-warnings=0 . && pnpm test && node --import ./scripts/tools-loader.mjs --experimental-strip-types .github/reviewer/__tests__/decide-and-merge.test.mjs && node --import ./scripts/tools-loader.mjs --experimental-strip-types .github/reviewer/__tests__/classify.test.mjs
verify_fix_cap: 3
verify_timeout_s: 1500
---

# Goal

Change the publish-gate's visual regression from a hard BLOCKER into an
informational EXHIBIT for admin/content publish PRs, while keeping it a hard
gate for normal engineering PRs.

## The problem (real, observed on PR #53)

The `/admin` content agent's whole job is to change copy and layout. When it
does (e.g. it swapped the header text wordmark for a 140px logo image, making
every page ~62px taller), the `visual-diff` job in
`.github/workflows/publish-gate.yml` fails because the freshly rendered pages
no longer match the committed baseline PNGs in `visual/__screenshots__/`. That
failure is then treated by `.github/reviewer/decide-and-merge.mjs` as a red
"deterministic" job, so `auto-merge-decision` blocks. Net effect: the gate
misfires on the exact thing the admin feature is designed to do. A pixel-match
gate is correct for engineering PRs (an unintended pixel change == a
regression) but wrong for agent-authored content PRs (a pixel change IS the
intent).

## The fix (design)

Discriminator: **admin publish PRs come from branches prefixed
`staging/admin/`** (see PR #53's head branch `staging/admin/2026-06-07-1014-l6hb5x`).
That prefix is the signal "this is an agent-authored content publish".

For PRs whose head branch starts with `staging/admin/`:
- The visual baseline mismatch must NOT block the merge gate. Implement this by
  having the `visual-diff` job run in **update mode** for these PRs: regenerate
  the baseline PNGs (`pnpm exec playwright test --config visual/playwright.config.ts --update-snapshots`),
  commit the regenerated `visual/__screenshots__/**` back to the PR's head
  branch (as a bot commit), and post a PR comment that links the
  playwright-report artifact / summarizes which pages changed so the human
  reviewer sees the visual delta. The job then exits success.
- Because the regenerated baselines are committed to the PR branch, they land
  on `main` naturally when the PR merges (no separate post-merge main-write
  job, no recursion risk). The next PR diffs against the new look.
- The safety net for these PRs is the existing adversarial `reviewer` matrix
  (ux/code/policy lenses) plus the human eyeballing the before/after, NOT the
  pixel equality.

For ALL OTHER PRs (any head branch not prefixed `staging/admin/`):
- `visual-diff` behavior is UNCHANGED: it runs the comparison, and a mismatch
  is a hard failure that blocks via `decide-and-merge.mjs` exactly as today.

`decide-and-merge.mjs` must treat a `visual-diff` result that was intentionally
made advisory (admin PR) as non-blocking, and keep treating it as a hard red
for non-admin PRs. Prefer to keep the discrimination in the workflow (the
admin-PR visual-diff job exits success after updating snapshots, so
decide-and-merge already sees green) rather than threading branch-name logic
deep into decide-and-merge, UNLESS decide-and-merge needs an explicit signal.
Whichever you choose, the unit tests must cover it.

## Read first

- `.github/workflows/publish-gate.yml` (the `visual-diff` and
  `auto-merge-decision` jobs; note `auto-merge-decision.needs` includes
  `visual-diff`, and the `deterministic` JSON it builds includes
  `"visual-diff"`).
- `.github/reviewer/decide-and-merge.mjs` (the fail-closed logic; how it reads
  the deterministic job map).
- `.github/reviewer/__tests__/decide-and-merge.test.mjs` and
  `.github/reviewer/__tests__/classify.test.mjs` (the test patterns + the
  tools-loader invocation).
- `.github/reviewer/classify.mjs` and `src/lib/zones.ts` (how zones are
  computed; you may reuse the zone signal but the PRIMARY discriminator for
  THIS change is the `staging/admin/` head-branch prefix, because engineering
  PRs also touch the `components` zone).
- `visual/README.md`, `visual/playwright.config.ts`, `visual/pages.spec.ts`
  (how the baselines are generated; the pinned arm64 Playwright container the
  baselines were made in: `mcr.microsoft.com/playwright:v1.60.0-noble`). Any
  snapshot regeneration MUST happen inside that same pinned container/runner so
  the new PNGs match CI rendering.

## Definition of done

- An admin publish PR (head branch `staging/admin/**`) with a layout change
  does NOT get blocked by `visual-diff`: the job updates + commits the
  baselines to the PR branch, posts an informational comment, and exits
  success, so `auto-merge-decision` no longer sees a red deterministic job from
  the visual change.
- A normal engineering PR (any other branch) with an unintended visual change
  STILL fails `visual-diff` and is STILL blocked. Unchanged.
- New/updated unit tests in `.github/reviewer/__tests__/` cover both paths
  (admin-PR visual-diff advisory; non-admin visual-diff hard-block). Follow the
  existing tools-loader test invocation pattern.
- The bot commit that writes regenerated snapshots to the PR branch uses a
  GitHub-linked author identity (do NOT introduce a new author email that
  isn't a GitHub account; reuse the workflow's existing token/author pattern,
  e.g. github-actions[bot]). Em/en dashes are forbidden everywhere (the
  `dash-guard` job enforces U+2014 / U+2013 rejection; keep all added lines
  clean).
- The `verify` command in this goal's frontmatter passes.
- Single commit on this branch with a conventional-commit message explaining
  WHY (the admin-content-PR vs engineering-PR distinction).

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push to any
  remote (the operator pushes + opens the PR).
- DO NOT touch: any deployment infra (`deploy.yml`, Dockerfile, entrypoint),
  the admin host, Vercel config, DNS, `src/lib/deck-core/**` (being migrated
  out to lumitra-studio), or the email-author logic in `src/lib/auth-session.ts`
  / `src/lib/admin/git-identity.ts` (handled separately).
- Do not weaken the gate for non-admin PRs in any way. The engineering-PR path
  must remain byte-equivalent in behavior.
- Do not run destructive commands.
- When done, output a final message that the task is complete.

## Notes

- You cannot run the actual Playwright visual job locally on this machine (it
  needs the arm64 Linux container). That is fine: your `verify` gate covers the
  decide-and-merge logic + lint + types + unit tests, which is where the
  correctness lives. The screenshot regeneration itself runs in CI.
- If you discover the cleanest implementation needs a small helper or a new
  workflow step input, that is in scope. Keep the change cohesive and minimal.
- If `decide-and-merge.mjs` already has a notion of "advisory" or
  "soft" jobs, reuse it rather than inventing a parallel mechanism.
