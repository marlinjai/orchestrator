---
task: storage-brain-lint-and-ci
verify: pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test
verify_fix_cap: 3
verify_timeout_s: 1200
---

# Goal

Make storage-brain's quality gates real: (1) fix the ~199 pre-existing eslint errors so
`pnpm run lint` is GREEN, and (2) add a CI workflow that runs build + typecheck + lint + test on
every PR, so these gates can never silently rot again (the repo currently has ONLY deploy
workflows, never ran eslint/tsc in CI).

## Context

`pnpm run lint` on `main` reports ~199 errors / 9 warnings (208 problems). This is pre-existing
debt: CI only runs deploy workflows + `vitest` locally, so eslint and `tsc --noEmit` were never
enforced and rotted. `tsc --noEmit` was already fixed to green in a prior slice; this slice does
lint + CI enforcement.

## Definition of done

- `pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test` ALL green (lint green is
  the whole point of this slice).
- A CI workflow (e.g. `.github/workflows/verify.yml`) that runs on `pull_request` (and pushes to
  `main`): `pnpm install --frozen-lockfile`, then build, typecheck, lint, test. Mirror the
  node/pnpm setup already used in `.github/workflows/deploy-api.yml` / `deploy-dashboard.yml`
  (same Node version, same pnpm action). Do NOT touch the deploy workflows.
- Single commit (a second commit for the workflow is fine; they squash), conventional message.

## How to fix the lint errors (DECIDED POLICY — Option A)

Lint is ~1442 errors. ~1353 are the type-aware `no-unsafe-*` family
(`no-unsafe-member-access`, `no-unsafe-assignment`, `no-unsafe-call`, `no-unsafe-argument`,
`no-unsafe-return`), almost entirely in TEST files (untyped mocks, `await res.json()`). Decided
policy (Marlin, 2026-06-17):

1. **Relax the `no-unsafe-*` family for TEST FILES ONLY** via an eslint `overrides` block scoped to
   `**/*.spec.ts` (and any test setup files). Turn OFF exactly: `no-unsafe-member-access`,
   `no-unsafe-assignment`, `no-unsafe-call`, `no-unsafe-argument`, `no-unsafe-return` for that
   glob. This is standard practice (tests use loose mocks); it is NOT a global weakening.
2. **Source (`src/**` non-spec) stays STRICT.** Do not relax any rule for source. Fix every real
   `src/` lint error properly (proper types, remove unused, `await`/`void` floating promises,
   nullish coalescing, etc.). Do NOT silence source errors with disables except for genuinely
   intentional code with a scoped `// eslint-disable-next-line <rule> -- <reason>`.
3. Known intentional case: `packages/shared/src/schemas.ts` `no-control-regex` on the `\x00-\x1f`
   range is correct (rejects control chars in filenames) -> scoped disable with that reason.
4. Run `eslint --fix` first for the ~17 auto-fixable, then handle the rest.
5. Do NOT change runtime behavior. If a lint fix would change behavior, file an `open_thread`.

After this: `pnpm run lint` must be GREEN, with `no-unsafe-*` still ENFORCED on `src/`.

## Constraints

- Stay in this worktree. Do not push. No em-dashes or en-dashes in anything you write.
- The ONLY permitted eslint-config change is the `**/*.spec.ts` override in step 1. Do NOT turn any
  rule off for `src/`, and do NOT weaken rules repo-wide.
- Do not modify the deploy workflows.

## Notes

- This is the "gates must match reality" follow-up: once CI enforces build/typecheck/lint/test,
  future PRs (including the deferred auth-brain machine-key slice) get caught automatically.
- If you find lint errors that reveal real bugs (not just style), fix the bug and note it in the
  commit body.
