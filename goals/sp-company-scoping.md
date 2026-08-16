---
task: sp-company-scoping
spec: docs/plans/2026-08-16-multi-tenancy.md
depends_on: [sp-tenancy-gate]
shared_state: [lockfile, prisma, migrations, env]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Implement **slice S3** of `docs/plans/2026-08-16-multi-tenancy.md`: scope every
project, media item and post to a company, so two companies using
social.lumitra.co cannot see or touch each other's data.

Slice S2 (already merged) gates access on the per-company `social` app grant and
exposes the resolved **companyId** (`activeWorkspace.tenantId`) from the session.
This slice makes that id actually load-bearing in the data layer.

This is the slice that makes tenancy real. Correctness matters more than speed.

## Read first

- `docs/plans/2026-08-16-multi-tenancy.md`, S3 especially
- `prisma/schema.prisma` (Project, Media, Post, SocialAccount)
- `src/lib/auth.ts` as S2 left it: this is where `companyId` comes from. Read it
  fresh, do not assume its shape from this goal file.
- `src/lib/projects.ts` (`PROJECT_SEED`, `ensureProjects`, both being deleted)
- EVERY route under `src/app/api/`, one by one
- `src/app/api/projects/[slug]/grid/reorder/route.ts`: the reference example of
  the bug class this slice eliminates. It was fixed in PR #2 to scope by project.
  Now it, and everything else, must scope by COMPANY.

## Definition of done

- `Project.companyId String` (the auth-brain tenant id), indexed. `slug` loses
  its global `@unique`, replaced by `@@unique([companyId, slug])`, because two
  companies may both want a `main` project.
- A Prisma migration that:
  - adds the column and the composite unique;
  - **deletes the old seeded projects ONLY if they have no media and no posts**;
  - **aborts loudly** (raises) if any project holds content, rather than
    guessing an owner or silently dropping it. Marlin then assigns it by hand.
    Prod is believed empty, but "believed" is not "verified", and silent data
    loss is unacceptable.
- `PROJECT_SEED` and `ensureProjects` deleted. Projects are created by users, per
  company. Add the minimal create-project flow needed for that (name, slug,
  igHandle, language, brand voice) plus its API route, guarded like the rest.
- **Every read and every write filters by the session's `companyId`.** Routes
  resolve a project by `(companyId, slug)`, never by slug alone.
- `/api/posts/[id]` and `/api/media/[id]` (and anything else keyed by a bare id)
  must verify the row belongs to the caller's company before returning or
  mutating it. A foreign id returns 404 (do not leak existence via 403 on a
  by-id read; use 404 for by-id, 403 only where the caller named a project it
  cannot access).
- **Never** read a company id from a request body, query parameter, header or
  cookie. It comes from the verified session only.
- Storage Brain object keys get a company prefix so media cannot collide or leak
  across companies. Existing keys: handle the empty-prod case simply; do not
  build a migration for objects that do not exist.
- Tests, and this is the core deliverable: for EVERY route, a case where a user
  in company A attempts to read and to mutate company B's project, media and
  post, expecting 404/403 and asserting the store is unchanged. A test that only
  proves the happy path does not count as covering this slice.
- Existing tests keep passing. Update them for the new signatures where needed,
  but do NOT delete assertions or weaken them to get green.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** The app is
  live at social.lumitra.co. Write the migration; do not run it against prod.
- Do not build scheduling, publish queue, Resend email, or the erasure consumer
  (that is S4).
- Do not weaken or delete existing tests to get a green build.

## Notes

- Real tenants for context: the `sharondisalvo` tenant group holds two companies,
  `opuntia` and `return-hypnosis`, each with a `main` workspace. So two distinct
  companies really will use this app, and one of them is not Marlin. This is not
  a hypothetical boundary.
- The company id is an auth-brain tenant id (a UUID-shaped string). Store it as a
  plain indexed String; there is no FK to auth-brain from this database.
- If a route cannot be made safe without a bigger refactor, do the refactor here
  rather than leaving a scoped-by-id hole and filing a thread. A half-scoped app
  is the same security posture as an unscoped one.
- Think adversarially while writing the tests: the question is not "does the
  happy path work" but "can a determined authenticated user in company A reach
  company B's data through ANY route in this app".
