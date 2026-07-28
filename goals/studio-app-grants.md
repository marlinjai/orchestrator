---
task: studio-app-grants
verify: pnpm db:generate && pnpm test && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice B of the app-entitlements plan: Lumitra Studio consumes auth-brain `app_grants` as its enablement source and DELETES its own `StudioTenant` registry. The governing plan (including the binding "Critical review addenda") is `docs/plans/2026-07-24-app-entitlements.md` in the AUTH-BRAIN repo; its content as it binds Studio is summarized here in full, so treat THIS file as authoritative for the slice.

## Precondition (run FIRST, abort loudly on failure)

`npm view @marlinjai/auth-brain-sdk@1.3.0 version` must print `1.3.0` (and `npm view @marlinjai/auth-brain-shared@1.2.0 version` must print `1.2.0`). If not, STOP immediately and report: the dependency publish has not happened and this slice cannot proceed. Do not work around it.

## Read first

- `src/lib/auth/verifyRequest.ts`, `src/lib/auth/can.ts`, `src/lib/tenant/access.ts`, `src/middleware.ts`
- `src/app/api/admin/tenants/route.ts` + its spec (this surface is being DELETED)
- `prisma/schema.prisma` (`StudioTenant` model, being DELETED)
- `src/lib/tenant/isolation.spec.ts`, `src/lib/auth/__tests__/*`, `src/middleware.spec.ts`
- The updated SDK types: `@marlinjai/auth-brain-sdk@1.3.0` / `-shared@1.2.0`: `tenants[]` entries in the session verify response and the api-key verify scope now carry `app_grants: string[]`

## Definition of done

1. **Dependency bump**: `@marlinjai/auth-brain-sdk` to `^1.3.0` (and `-shared` to `^1.2.0` if directly depended on); lockfile updated.
2. **Browser gate**: enabled tenants = `session.tenants[]` entries whose `app_grants` contains `'studio'`. The `isTenantEnabled`/`StudioTenant` lookup is gone. SKEW DETECTION (plan addendum 6): if the verify response's tenant entries carry NO `app_grants` field at all (older auth-brain build), treat as zero grants (fail closed) but log a DISTINCT error string, e.g. `verify response carried no app_grants field (auth-brain version skew?)`, so an auth-brain rollback is diagnosable in seconds and distinguishable from a merely-ungranted user. Never log the session itself.
3. **Service gate**: the api-key verify response's scope `app_grants` must contain `'studio'`; a tenant-scoped key whose company lacks the grant is 403 (`no-tenant-access` reason), preserving all existing fail-closed semantics (unknown/revoked key, wrong scope type, auth-brain failure unchanged).
4. **Deletion, complete**: `StudioTenant` model + a migration dropping the table; `src/lib/tenant/access.ts`; `/api/admin/tenants` route and spec (its job moved to auth-brain's machine API); the now-unused `ADMIN_API_KEY` env handling and every reference (code, env examples, docs). No parked code, no legacy fallbacks.
5. **Tests**:
   - Existing isolation/gate suites green with the new source of truth (update mocked verify payloads to carry `app_grants`).
   - A tenant WITH membership but WITHOUT the `studio` grant: request-access page (browser) / 403 (service key).
   - Revision paths (addendum 8): grant present -> revoked (next request loses access, both browser and key paths) -> re-granted (access returns, no stale state).
   - Skew: tenant entries lacking the `app_grants` field entirely -> fail closed + the distinct log line (assert the log seam, not stdout).
   - Wire-contract (addendum 7): the gate logic is exercised against a REAL response fixture parsed through the published shared zod schemas, not only hand-rolled mocks.
   - Admin-route removal: `/api/admin/tenants` now 404s (no stale handler).
6. `pnpm db:generate && pnpm test && pnpm lint` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push.
- Do not change the data-scoping filters, stamping logic, brand/project/run models (beyond removing StudioTenant), or the browser session verification flow beyond the grant source swap.
- Do not add any OpenFGA usage.
- Fail closed on every path; never log keys, cookies, or session bodies.
- No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.

## Notes

- Rollback recipe (goes in the PR description, not code): redeploy the previous image; re-create the two enablement rows via the old admin API if that image is pre-#111... for the CURRENT previous image (post-#111) the recipe is: `POST /api/admin/tenants` for `lumitra-core` `019ec2f2-f19e-70f4-a889-8afb34c314ca` and Opuntia `019f944b-bc25-73c1-be1f-d160c6488694` with the ADMIN_API_KEY, and note the dropped table must be restored by re-running the deleted migration's inverse (CREATE TABLE) first. Keep the recipe verbatim in the PR body.
- The two grants are ALREADY SEEDED in auth-brain prod (`studio` x both tenants), so deploy order is safe the moment this merges.
