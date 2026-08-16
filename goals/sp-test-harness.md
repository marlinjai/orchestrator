---
task: sp-test-harness
shared_state: [lockfile]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Give `social-planner` a real test harness. The repo currently has ZERO tests, no
typecheck script, and `lint` is a bare `eslint` call. That means nothing can gate a
change to this repo. This slice establishes the harness and covers the Phase 1 logic
that already exists, so later slices (AI captions, scheduling) can be verified.

This is infrastructure plus tests only. Do NOT add product features.

## Read first

- `package.json` (scripts, deps: Next.js 16, React, Prisma 7 with `@prisma/adapter-pg`)
- `prisma/schema.prisma` (models: Project, Media, Post, SocialAccount)
- `src/lib/db.ts` (a lazy Proxy around PrismaClient, constructed on first property
  access so `next build` works with no database; preserve this property)
- `src/lib/auth.ts` (Auth Brain session verification via `@marlinjai/auth-brain-sdk`)
- `src/lib/projects.ts`, `src/lib/storage.ts`
- Every route under `src/app/api/` (projects, media, posts, grid, grid/reorder)
- `docs/plans/2026-07-12-social-planner-design.md` section 7.1 for the intended
  planner behavior
- `.github/workflows/deploy.yml`

## Definition of done

- **Vitest** installed and configured for this Next.js App Router repo. Add a
  `test` script (non-watch, suitable for CI) and a `typecheck` script running
  `tsc --noEmit`.
- Tests covering the logic that exists today. At minimum:
  - **Grid reorder** (`src/app/api/projects/[slug]/grid/reorder/route.ts`): this is
    the highest-value target. Cover reordering within the grid, moving a post to an
    occupied position, and that `gridPosition` values stay unique and contiguous per
    project. Assert on the resulting ordering, not just on a 200 status.
  - **Auth guards**: `requireApiAuth` returns 401 with no cookie and passes with a
    valid session; `requireAuth` redirects when unauthenticated. Mock the Auth Brain
    SDK, do not hit the network.
  - **Project resolution** in `src/lib/projects.ts` (unknown slug, valid slug).
  - **Media upload route**: rejects unauthenticated requests, and stores the returned
    Storage Brain key on the Media row. Mock the Storage Brain SDK, do not hit the
    network.
- Prisma is mocked at the `src/lib/db.ts` boundary. Do NOT require a live Postgres,
  Docker, or testcontainers to run `pnpm test`. The suite must pass on a bare machine
  with no database and no network.
- `.github/workflows/deploy.yml` runs `pnpm test` and `pnpm typecheck` before the
  image build, so the tests actually gate deploys.
- Fix any real type errors that `tsc --noEmit` surfaces. If a fix would change runtime
  behavior rather than just types, record it with `update_state(kind="open_thread")`
  and leave the behavior alone.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** This repo's prod
  deployment is live at social.lumitra.co. Tests must never connect to a real service.
- Do not change `prisma/schema.prisma`. No migrations in this slice.
- Do not add product features (no AI, no scheduling, no publish queue). Those are
  separate slices.
- Preserve the lazy-Proxy pattern in `src/lib/db.ts`. It exists so `next build` can
  collect route metadata without a database. Breaking it breaks the Docker build.

## Notes

- Node 22, pnpm 11, pinned via `packageManager`.
- Prefer Vitest over Jest: faster, and it handles the repo's ESM plus TypeScript setup
  with far less configuration.
- The app authenticates via Auth Brain (`lumitra_session` cookie, hosted at
  auth.lumitra.co). There is no local credential to test against, so mocking the SDK
  is the only correct approach.
- If you find real bugs in the Phase 1 code while writing tests, that is a valuable
  result: fix the small clear ones in this slice, and file anything larger with
  `update_state(kind="open_thread")` rather than expanding scope silently.
