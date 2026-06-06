---
task: flowmap-drop-default-flow
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice D)
depends_on: [flowmap-thumbs-storage-brain]
shared_state: [prisma, migrations]
---

# Goal

Implement Slice D of the flowmap-next handover: remove the now-inert `defaultOnboardingFlow` value. Nothing reads it after the voice-first onboarding consolidation, so it is dead weight across the API, the admin settings UI, the DTO, the specs, and the Prisma schema. Remove it cleanly, including a migration to drop the column.

## Read first

- Each file in the removal table below, to confirm the current shape before editing.
- `apps/api/prisma/schema.prisma`: the `AppSettings` model.
- The repo's existing migration conventions under `apps/api/prisma/migrations/`.

## Scope: exact removal sites (verified in the handover)

| # | File | Remove |
|---|------|--------|
| 1 | `apps/api/src/modules/onboarding/onboarding.controller.ts` | the `@Get('default-flow')` method; the `AppSettingsService` import + constructor param if now unused |
| 2 | `apps/api/src/modules/admin/app-settings.service.ts` | `DEFAULT_ONBOARDING_FLOW` const; `defaultOnboardingFlow` from `AppSettingsView`; the 3 `get()` fallback returns; `getDefaultOnboardingFlow()`; the `update()` input field; the 4 Prisma upsert payload sites |
| 3 | `apps/api/src/modules/admin/dto/update-app-settings.dto.ts` | `ADMIN_ONBOARDING_FLOWS` + `AdminOnboardingFlow`; the `defaultOnboardingFlow` DTO field |
| 4 | `apps/api/src/modules/admin/admin-settings.controller.ts` | `ADMIN_ONBOARDING_FLOWS` import; `allowedOnboardingFlows` from the response; `defaultOnboardingFlow` from the service call |
| 5 | `apps/web/src/app/admin/settings/settings-client.tsx` | the whole "Default onboarding flow" UI section + its state/dirty/save plumbing |
| 6 | specs (`admin-settings.controller.spec.ts`, `app-settings.service.spec.ts`, + 1 more) | the `defaultOnboardingFlow` mocks/assertions |
| 7 | `apps/api/prisma/schema.prisma` | the `defaultOnboardingFlow` column on `AppSettings` + a migration to drop it |

After editing, re-grep to confirm zero references:

```bash
grep -rin "defaultOnboardingFlow\|default-flow\|DEFAULT_ONBOARDING_FLOW\|ADMIN_ONBOARDING_FLOWS\|AdminOnboardingFlow\|allowedOnboardingFlows\|getDefaultOnboardingFlow" apps/ packages/
```

It should return nothing (outside the migration SQL itself and the handover doc, which is not on this branch).

## Definition of done

- `grep -rin "defaultOnboardingFlow\|default-flow"` across `apps/` and `packages/` is empty (migration SQL excepted).
- `pnpm --filter @lola/api test` passes; the removed specs/assertions are gone, the rest green.
- `pnpm --filter @lola/api exec tsc --noEmit` clean; web typecheck clean.
- A migration to DROP the `defaultOnboardingFlow` column exists under `apps/api/prisma/migrations/`; `prisma generate` run.
- The admin settings page still compiles and renders (the removed section leaves no dangling state).
- Conventional-commit, subject lowercase after the colon, e.g. `refactor(onboarding): remove inert defaultOnboardingFlow setting`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- No em-dashes or en-dashes. Use colons, parentheses, commas, periods.
- This is a removal, not a behavior change: do not "improve" adjacent code. Keep the diff scoped to deleting the dead setting and whatever becomes unused as a direct consequence.

## Notes: running the migration (IMPORTANT, avoids shared-DB drift)

This worktree shares the Docker postgres (`lola-stories-postgres-1`, port 5432) with the main repo and other worktrees. Use a dedicated per-worktree database for `prisma migrate dev` ONLY:

```bash
docker exec lola-stories-postgres-1 psql -U lola -d lola_stories \
  -c "CREATE DATABASE lola_orch_flowmap_d;"
DATABASE_URL='postgresql://lola:lola_dev@localhost:5432/lola_orch_flowmap_d' \
  pnpm --filter @lola/api exec prisma migrate dev --name drop_default_onboarding_flow
```

(`lola_dev` is the committed local-dev password from `docker-compose.yml`.) Against the fresh DB, prisma applies all of main's migrations, then creates + applies the drop. Do NOT resolve any drift error by copying another branch's migration into this branch. Optionally drop the DB when done.

## Notes: general

- `pnpm install` the worktree, `pnpm --filter @lola/api exec prisma generate` after the schema edit.
- If anything contradicts repo conventions, prefer the conventions and record it via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message that Slice D is complete, confirming the grep is empty and naming the drop migration.
