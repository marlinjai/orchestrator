---
task: framer-ci-integration-tests
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Add the FIRST real continuous-integration test workflow to framer-clone. Today the repo has NO test
workflow: the only `.github/workflows/` file is `docs-trigger.yml`, and the sole automated check on a
PR is a GitGuardian secret scan (a GitHub App, not a workflow). So local `pnpm` verify is currently the
only correctness gate. Build a GitHub Actions workflow that runs the full verify suite on every push
and pull request to `main`, INCLUDING the integration tests (`pnpm test:integration`), which run
nowhere today.

## Read first

- `package.json` scripts: `build` (`next build`), `lint` (`eslint .`), `test` (`vitest run`),
  `test:integration` (`vitest run --config vitest.integration.config.ts`). Note the exact script names.
- `vitest.integration.config.ts` and `vitest.integration.setup.ts`: the integration run uses a
  `globalSetup` that stands up a **Dockerized Postgres** (container boot + migrate), and co-located
  `src/**/*.itest.ts` files boot their OWN throwaway Postgres in `beforeAll`. Read the setup file to
  learn EXACTLY what it needs at run time (Docker availability, any env vars / DATABASE_URL ownership,
  migrate step). The CI job must satisfy those requirements so integration tests actually pass, not just
  get invoked.
- `.github/workflows/docs-trigger.yml`: the repo's existing workflow style (action versions, triggers).
  Match its conventions where sensible. Do NOT modify or break it.
- The scaffold-project canonical CI conventions: pnpm + Node setup, dependency cache, `prisma generate`
  before typecheck/build, a Postgres-capable job for DB-touching tests. If a canonical REUSABLE verify
  workflow exists in the org (e.g. a `marlinjai/.github` shared workflow referenced via `uses:`),
  prefer wiring to it; otherwise write a self-contained workflow.

## Definition of done

- A new `.github/workflows/ci.yml` (name it clearly, e.g. `CI` / `verify`) triggered on
  `push` to `main` and `pull_request` targeting `main`, with a sensible `concurrency` group to cancel
  superseded runs.
- The workflow runs, in order, against the repo's real toolchain (pnpm, the Node version the repo
  targets): install deps, `prisma generate`, `pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm test`,
  `pnpm build`, and `pnpm test:integration`. Use a dummy `DATABASE_URL` for the steps that only need
  the Prisma client generated / Next build (they do not connect); let the integration `globalSetup`
  own the real test database exactly as it does locally.
- The integration step runs on a runner where the `globalSetup`'s Dockerized-Postgres path works
  (`ubuntu-latest` has Docker preinstalled). If the setup uses a `services:` Postgres instead of
  Docker-in-Docker, wire the service container + the env the setup expects. Whichever the setup file
  actually requires, make it pass. Do NOT weaken or skip the integration tests to make the job green.
- pnpm store caching wired so CI is not re-downloading the whole store every run.
- Single commit, conventional-commit message describing the WHY (first real CI test gate for the repo).

## Constraints

- Additive only: do NOT modify `docs-trigger.yml`, app source, the Prisma schema, or any migration.
  This slice is parallel-safe (no shared_state with the content-agent or commerce slices).
- Do NOT relax, skip, or `--passWithNoTests` your way past any test to make the job pass. If a test or
  the integration setup is genuinely broken on a clean checkout, STOP and report it rather than
  papering over it.
- No secrets as literals in the workflow. If a step needs a token (none expected for the test suite),
  reference a GitHub secret, never inline it.
- No em-dashes or en-dashes anywhere (workflow yaml, comments, commit message).
- Stay in this worktree. Do not push to any remote (the operator handles PR + merge, and verifies the
  workflow itself runs green on the PR — the in-worktree verify gate cannot exercise the YAML). Do not
  run destructive commands. When done, output a final completion message.

## Notes

- The authoritative proof for THIS task is the operator watching the new workflow run green on the PR
  (the local verify gate only confirms the repo still typechecks/lints/unit-tests). Make the workflow
  correct on the first push: read `vitest.integration.setup.ts` carefully so the integration job has
  exactly what it needs.
- If the Node version is pinned anywhere (`.nvmrc`, `engines`, `package.json`), honor it in the
  `setup-node` step rather than hardcoding a different major.
