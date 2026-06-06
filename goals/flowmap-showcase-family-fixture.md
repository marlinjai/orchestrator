---
task: flowmap-showcase-family-fixture
spec: follow-up to PR #214 (per-device screenshots) - the shared prod "showcase" family
---

# Goal

Build the shared "showcase" family fixture as a STANDALONE, idempotent, non-destructive seed script that can be pointed at any database (including prod, later, deliberately) to create ONE curated family used for the `/admin/flow` web previews. Everyone (Marlin, Leon, the capture bot) sees the same family because the web screenshots are captured from this one account. This task builds + tests the script ONLY. It does NOT run against prod and does NOT change the dev seed's production guard.

The whole point: the web flowmap previews need a populated family to look like anything, and the existing demo fixture ("Familie Berger") is hard dev-only (`NODE_ENV !== 'production'` guard in `prisma/seed.ts`). This script promotes that SAME fixed-id content into a standalone, explicitly-invoked seed so it can populate a single shared showcase family wherever we choose to run it.

## Read first

- `apps/api/prisma/seed.ts`: `seedDemoFlowmap(ownerId)` ("Familie Berger", fixed ids/slugs: `FAMILY_ID`, the children, relatives, the sample story). This is the content to reuse VERBATIM (same fixed ids) so the flowmap preview-route annotations in `apps/web/flowmap.annotations.ts` keep resolving against it.
- `apps/web/flowmap.annotations.ts` (the `previews` map): confirm which family/child/etc. ids the preview routes reference, so the showcase family carries exactly those ids.
- `apps/api/src/...` user/seed-admin lookup: how the seed admin account is identified (`SEED_USER_EMAIL`). The showcase family must be owned by that account so the capture (which logs in as the seed admin) renders it.
- `apps/api/package.json` scripts (e.g. `db:seed`, `prisma:seed:marketplace`) for the script + Infisical-wrapping convention.

## Scope and changes

- New standalone script `apps/api/prisma/seed-flowmap-showcase.ts`:
  - Resolves the owner by `SEED_USER_EMAIL` (the seed admin). If that user does not exist, FAIL with a clear message (do not invent an owner).
  - Seeds ONE family with the SAME fixed ids/slugs as `seedDemoFlowmap` (reuse the existing fixture definition: extract the shared family-shape into something both `seed.ts` and this script import, OR call a shared helper, so there is ONE source of truth, not a copy that can drift).
  - **Idempotent + NON-destructive (create-if-absent):** if the family / its children / relatives / story already exist (by fixed id), DO NOT overwrite their editable fields. This lets an admin edit the showcase family in the app and keep those edits across re-runs. (Contrast with the dev `seedDemoFlowmap` which upserts/updates.) Only create what is missing.
  - **Safety guard:** refuse to run unless an explicit confirmation env/flag is set (e.g. `FLOWMAP_SHOWCASE_CONFIRM=1`), and BEFORE writing, print the resolved database host + the owner email it will seed under, so an operator can see exactly where it is about to write. No silent prod writes.
  - Add a package script (e.g. `"prisma:seed:flowmap-showcase": "tsx prisma/seed-flowmap-showcase.ts"`); document the Infisical-wrapped invocation in the file header (dev DB and, later, prod with the deployed `DATABASE_URL`).
- Do NOT modify the `NODE_ENV` guard in `seed.ts`. The dev demo fixture stays dev-only; this standalone script is the explicit, owner-scoped, confirm-gated path for the shared showcase family.

## Definition of done

- `pnpm --filter @lola/api exec tsc --noEmit` clean; `pnpm --filter @lola/api test` passes.
- Unit test (mocked PrismaService) proving: (a) it creates the family + members when absent, (b) it does NOT overwrite existing editable fields when they already exist (non-destructive), (c) it refuses to run without the confirmation flag, (d) it fails clearly when the seed-admin user is absent.
- The family/children/relatives/story ids match the dev fixture exactly (so `flowmap.annotations.ts` preview routes resolve).
- No change to `seed.ts`'s production guard.
- Conventional-commit, subject lowercase after the colon, e.g. `feat(api): standalone idempotent flowmap showcase family seed`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- DO NOT run the script against any remote/prod database in this task. Build + unit-test only. The operator runs it deliberately later.
- No em-dashes or en-dashes anywhere. Use colons, parentheses, commas, periods.
- One source of truth for the fixture content: do not copy-paste the Familie Berger definition into a second place that can drift; share it between `seed.ts` and the new script.

## Notes

- `pnpm install` the worktree, then `pnpm --filter @lola/api exec prisma generate`. No migration (the `FlowmapThumbnail` per-device migration already landed in #214; this task adds no schema change).
- Unit tests mock Prisma; no live DB needed.
- Commitlint: lowercase subject after the colon. The repo squash-merges; a Marlin-authored PR needs no bridge commit.
- If the existing `seedDemoFlowmap` is not cleanly extractable (e.g. it inlines the owner creation), refactor minimally so the family-shape is shared, and note the refactor in the commit body. Prefer repo conventions; record any deviation via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message naming: the new script + its confirm guard, the shared fixture helper, the unit tests, and the exact Infisical-wrapped command an operator would run to seed a target DB.
