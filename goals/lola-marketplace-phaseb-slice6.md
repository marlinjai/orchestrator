---
task: lola-marketplace-phaseb-slice6
spec: docs/specs/2026-05-26-marketplace-phaseb-slice6-admin-ui-api-rewire.md
depends_on: [lola-marketplace-phaseb-slice5]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice6-admin-ui-api-rewire.md` end-to-end. Rewire the `/admin/marketplace` web UI from `marketplace-admin-store.ts` localStorage state to the new admin API endpoints that slice 5 just shipped. Delete the localStorage store. Form saves via API, optimistic update, toast on success/failure.

## Read first

- The spec file in full
- The parent plan section "Web Changes -> /admin/marketplace" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/web/src/app/admin/marketplace/marketplace-admin-store.ts` (the localStorage store being deleted)
- `apps/web/src/app/admin/marketplace/marketplace-admin-client.tsx` and `story-form.tsx` (the UI being rewired)
- The slice-5 admin endpoints in `apps/api/src/modules/marketplace/admin-marketplace.controller.ts`
- The repo's existing pattern for admin-side mutations (look for SWR mutations or TanStack Query in admin pages; mirror)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/web test` passes
- `pnpm --filter @lola/web tsc --noEmit` clean
- `pnpm --filter @lola/web build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(web): admin marketplace UI saves via API`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- DELETE `apps/web/src/app/admin/marketplace/marketplace-admin-store.ts` and any localStorage code paths. This is the whole point of the slice.
- Form posts call the slice-5 endpoints. The /admin route is locale-free (per memory `reference_admin_locale_free_route`): never navigate to /admin via `@/i18n/navigation`; use plain `next/navigation`'s `useRouter` or plain `<a href="/admin/...">` links.
- Admin auth check: the page is already gated by the admin auth pattern in this repo; do NOT add a new client-side gate. If the API returns 401/403, surface the error in a toast.
- Optimistic update: on save, update the local store/SWR cache immediately, then revert on error with a toast.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The slice-5 endpoints use `:id` (the UUID), not `:slug`. The form was previously slug-keyed (because the static catalog used slugs); the rewired form must send the UUID for updates but can show the slug as a read-only field.
- If the existing admin grid relies on `MARKETPLACE_TEMPLATES` from the static catalog, replace that with a fetch to `GET /api/admin/marketplace/stories` (if slice 5 added a list endpoint; otherwise use `GET /api/marketplace/stories` with a query param that bypasses the PUBLISHED filter, OR add a small admin-list endpoint — read the slice-5 spec carefully before deciding).
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
