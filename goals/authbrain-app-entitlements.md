---
task: authbrain-app-entitlements
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement Slice A of the app-entitlements plan: first-class "which company may use which app" data in auth-brain. Read the FULL plan first: `docs/plans/2026-07-24-app-entitlements.md` in this repo, INCLUDING the "Critical review addenda" section, whose 12 numbered constraints are binding on this slice. This goal file summarizes; the plan doc governs.

## Read first

- `docs/plans/2026-07-24-app-entitlements.md` (the governing plan; addenda constraints 1, 2, 4, 5, 7, 8, 9, 10 bind this slice)
- `packages/app/src/lib/admin-auth.ts` (`requirePlatformAdminFromCookies`; the gate pattern every new admin surface must repeat per page AND per action)
- `packages/app/src/app/admin/orgs/` + `admin/users/` (console patterns; also the `revokeInvitationAction` ride-along fix, addendum 1)
- `packages/app/src/lib/openfga/sync-worker.ts` (`tuplesFor` default; addendum 2)
- `packages/shared/src/types.ts` (`OutboxEventType` closed union; session/api-key response types)
- `packages/app/src/lib/suite-apps.ts` + `src/app/page.tsx` + specs (launcher)
- `packages/app/src/app/api/sessions/verify/route.ts`, `api/verify/api-key/route.ts`
- `packages/app/src/app/settings/account/page.tsx`, `settings/companies/`
- Migrations directory for numbering conventions

## Definition of done

1. **Schema**: `app_grants` migration per the plan (unique live grant per app x tenant, `granted_by`, soft delete). Repository functions with slug-validated writes.
2. **Events**: `app_grant.granted` / `app_grant.revoked` added to `OutboxEventType`, enqueued by the flows, audit entries written. NO `tuplesFor` case; add the "audit-only by design" comment at the default (addendum 2).
3. **Machine API**: `GET/POST/DELETE /api/admin/machine/app-grants` (auth-brain `ADMIN_API_KEY`, `actor_email` audit attribution, unknown `app_slug` rejected 400 against the registry, unknown tenant 404). Idempotent grant (repeat POST 200/no-op or 409, pick one and test it).
4. **Admin console "Apps" tab**: per app, granted companies with grant/revoke; per-organization section showing its tenants' grants; "grant to all companies in this organization" bulk action (addendum 4); slug selection only from the registry; orphan-slug rows render as an error state (addendum 5). Gate: `requirePlatformAdminFromCookies` on the page AND every server action, with tests that an authenticated non-admin gets 403 on both (addendum 1).
5. **Ride-along**: `revokeInvitationAction` routed through an actor-attributed flow like its siblings (addendum 1).
6. **Verify exposure**: `sessions/verify` response: each `tenants[]` entry gains `app_grants: string[]`; `api/verify/api-key` response: the scope block gains `app_grants` for the scoped tenant. Shared zod schemas + TS types updated additively; `@marlinjai/auth-brain-shared` and `-sdk` package.json versions get a MINOR bump (do NOT publish; the operator publishes after merge).
7. **Launcher**: `SuiteAppAccess` union gains `{ kind: 'open' }` and `{ kind: 'app-grant' }`; studio entry becomes `{ kind: 'app-grant' }`; ungranted users see the card in a STATIC request-access state (discoverable, explains that a company must be enabled, no notify button; addendum 9); analytics stays open; receipts keeps its prefix rule (addendum 12). `visibleApps` signature extended accordingly; existing specs updated, new states tested.
8. **Navigation + vocabulary**: "Manage companies" link on the home page companies section and on `settings/account`; all USER-FACING "Tenants"/"tenant" labels on home, account, and settings pages become "Companies"/"company" (admin console keeps technical terms; addendum 10).
9. **Wire-contract test** (addendum 7): a test builds the REAL verify response via the route handler (or a captured real payload fixture) and parses it with the published shared zod schema; same for the api-key verify response.
10. **Revision-path tests** (addendum 8): grant -> revoke -> re-grant cycle correctness; a deleted-then-recreated tenant reusing a slug does not inherit old grants.
11. `pnpm test && pnpm typecheck && pnpm lint` green at repo root. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do not publish npm packages.
- Do not change membership semantics, signup, invitations (beyond the named ride-along), or the OpenFGA model.
- Do not implement any Studio-side changes (Slice B is separate and depends on this slice's deploy + SDK publish).
- Fail closed everywhere; never log keys/cookies/sessions.
- No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.

## Notes

- The Docker-liveness probe pattern for DB-backed specs is in `src/lib/flows/companies.spec.ts` (ping-based `dockerReachable`); reuse it.
- Grant seeding for the two currently-enabled tenants happens POST-MERGE by the operator via the new machine API; do not seed in a migration.
