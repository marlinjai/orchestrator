---
task: lumitra-core-extraction
spec: docs/specs/2026-05-25-lumitra-core-library-extraction.md
---

# Goal

Implement slice 1 of the Lumitra Studio internal-infra deploy v0.1: extract a `@marlinjai/lumitra-core` workspace package from `src/lib/providers/`, `src/lib/brand.ts` (filesystem-free), and the Zod schemas in `src/lib/jobs/types.ts`. Establish a pnpm workspace. Rewire the Next.js app and the three CLIs to import from the new package. Single conventional commit on the existing `feat/lumitra-core-extraction` branch in this worktree.

## Read first

- The spec at `docs/specs/2026-05-25-lumitra-core-library-extraction.md` (full contents: Goal, Scope, Acceptance criteria, Non-acceptance, Risks, Sequence)
- The hosted-shape decision at `docs/plans/2026-05-25-hosted-shape-decision.md` (context only)
- The current Next.js app: `src/lib/brand.ts`, `src/lib/types.ts`, `src/lib/providers/` (entire tree including tests), `src/lib/jobs/types.ts`, `src/lib/jobs/queue.ts`, `src/lib/jobs/repository.ts`, `src/lib/jobs/worker.ts`, `src/lib/jobs/handlers/`
- Every callsite of the moved code: `git grep` for `from .*lib/providers`, `from .*lib/brand`, `from .*lib/jobs/types`, `BRANDS_DIR`, `loadBrand`
- `package.json` (scripts, deps, current versions), `next.config.ts`, `vitest.config.ts`, `tsconfig.json`
- `CLAUDE.md` if present in the repo

## Definition of done

Per the spec's Acceptance criteria, verified end-to-end:

- `pnpm-workspace.yaml` exists at repo root with `packages: ['packages/*']`.
- `packages/lumitra-core/` exists with `package.json` (name `@marlinjai/lumitra-core`, `"private": true`, `tsup` build, dual ESM+CJS+`.d.ts`, target node20, `exports` field with subpaths `.`, `./providers`, `./brand`, `./jobs`).
- Providers (entire `src/lib/providers/` tree, all subdirs, all test files) moved to `packages/lumitra-core/src/providers/`. No file remains at the old path.
- Brand loader moved to `packages/lumitra-core/src/brand/`. `loadBrand` signature is `(brandRootDir: string, slug: string)`. Module-level `BRANDS_DIR` and `__dirname_esm` constants removed entirely. `git grep BRANDS_DIR` returns zero hits.
- Job Zod schemas (`GenerateImageJobInputSchema`, `Generate3DOptionsSchema`, `Generate3DJobInputSchema`, `Remesh3DJobInputSchema`, `Texture3DJobInputSchema`, `JobStatuses`, `JobKinds` and their inferred types) moved to `packages/lumitra-core/src/jobs/types.ts`. Job handlers/queue/repository/worker stay in the Next.js app and import schemas from `@marlinjai/lumitra-core/jobs` (or whichever subpath you wire).
- Next.js app, all three CLIs (`src/cli/generate.ts`, `src/cli/remove-bg.ts`, `src/cli/manage-library.ts`), and any API route or script that consumed the moved code now imports from `@marlinjai/lumitra-core` (or a subpath). Zero relative imports into the old locations remain.
- Each callsite of `loadBrand` passes a `brandRootDir` argument. CLIs and API routes pass `resolve(process.cwd(), "brands")` (or `resolve(__dirname, "../../brands")` from CLI scripts, whichever matches the existing process semantics).
- Root `package.json` has `"packageManager": "pnpm@9.x"` (pin to the exact minor pnpm version `pnpm --version` reports in the worktree). Add `"@marlinjai/lumitra-core": "workspace:*"` to root `dependencies`.
- `pnpm install --frozen-lockfile` succeeds (after lockfile regen if needed; commit the new lockfile).
- `pnpm --filter @marlinjai/lumitra-core build` produces a non-empty `dist/` with ESM, CJS, and `.d.ts`.
- `pnpm --filter @marlinjai/lumitra-core test` passes (all provider, brand, schema tests that moved with the source).
- `pnpm build` (Next.js app) passes. Typecheck green.
- `pnpm test` at repo root passes for every test that does NOT require a database. If DB-bound tests (job repository, anything hitting Prisma) fail because no DB is configured in the worktree, STOP and call `update_state` with `kind="open_thread"` describing exactly which tests need a DB, and continue. Do not invent a DB. Do not attempt `prisma migrate dev`.
- Spec file `docs/specs/2026-05-25-lumitra-core-library-extraction.md`: frontmatter `status: draft` becomes `status: in-progress` at the start of work, then `status: completed` at the end (use the `document-lifecycle` standard: plan statuses `draft | decided | in-progress | completed`).
- Single conventional commit on `feat/lumitra-core-extraction`: `refactor(core): extract @marlinjai/lumitra-core workspace package` with a body summarizing what moved and what the brand loader signature change is.

## Constraints

- **Stay in this worktree.** Path is `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-studio-orch-lumitra-core-extraction`. Do not modify files anywhere else.
- **Do not push to any remote.** No `git push`. The branch stays local. Marlin gates and pushes manually.
- **Do not touch the database.** No `prisma migrate dev`, no `prisma db push`, no docker-compose ops. Read-only Prisma operations (`prisma generate`) are fine.
- **Do not change provider behavior.** This is a relocation, not a rewrite. The Vertex / KIE / OpenRouter / Studio3D provider implementations are byte-for-byte preserved (modulo import path edits within them).
- **Do not change Prisma schema or migrations.** Out of scope.
- **Do not add new dependencies** beyond what is strictly needed for the workspace package itself (likely just `tsup` as a devDep on the lib, and whatever Zod / provider SDK versions already exist in root `package.json` lifted into the lib's own `dependencies`). If you think you need a new runtime dependency, escalate.
- **Naming**: never use bare `LUMITRA_*` for env vars; always `LUMITRA_STUDIO_*`. (Not expected to touch env vars here, but stated for the chain.)
- **Typography**: no em-dash `—` or en-dash `–` anywhere, including commit message, spec status updates, code comments. Use colons, parentheses, commas, periods. Hyphens in compound words are fine.
- **No `--no-verify`**, no `--amend` after the initial commit, no force operations.
- **Conventional commit only.** No "WIP", no "fix typo", no follow-up commits to clean up the first one. If a mistake lands, fix it forward and combine with an interactive sequence, then squash into the single final commit before the run ends.

## Escalation triggers

Stop and escalate (via `update_state` with `kind="escalation"`) if:

- A test failure that is NOT a path-rewrite or workspace-resolution issue. (Path issues you fix; behavior changes you do not.)
- A circular import emerges between brand and providers that requires non-mechanical refactoring of either.
- Vitest cannot discover tests in `packages/lumitra-core/` even after standard workspace config. (Mention what you tried.)
- `pnpm --filter @marlinjai/lumitra-core build` fails with a tsup config issue you cannot resolve with the standard dual-ESM-CJS recipe.
- The brand loader has callers you cannot map to a sensible `brandRootDir`.
- You find yourself wanting to expand scope (move job handlers, change provider behavior, touch Prisma): stop.

## Notes

- Worktree base branch: `feat/hosted-shape-decision` (the spec lives there). The worktree branch is `feat/lumitra-core-extraction` already created off that base.
- Pinned pnpm version: read what's already installed via `pnpm --version` in the worktree. Use that as the `packageManager` field value (e.g. `pnpm@9.15.0`). Do not upgrade pnpm in this slice.
- This slice is independent of slices 2 (`service-token-auth-middleware`) and 3 (`coolify-deploy`). Those are not yours to touch; ignore their spec files.
- The hosted-shape decision answers four architectural questions: lib extraction is in scope (this slice), domain is `studio.lumitra.co`, worker stays lazy in-process, Postgres gets a new Coolify-managed instance. None of those affect your work directly, but if you read the spec or the handover and feel pulled toward them, return focus to this slice.
- When you write the final commit, include the spec status change (`draft -> completed`) in the same commit, not a separate one.
- Final message at the end of the run: confirm the branch name, the commit SHA, the package version of `@marlinjai/lumitra-core` in its `package.json` (`0.1.0`), and any `open_thread` entries you filed.
