---
task: authbrain-ownership-transfer
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1500
---

# Goal

Slice E1 of the GDPR erasure plan: ownership transfer for companies. Read the governing plan FIRST: `docs/plans/2026-07-24-gdpr-erasure.md` in this repo (it defines the legal model and why transfer is the unblock path for account erasure). This slice is ONLY the transfer mechanics; the erasure state machine is slice E2 and must not be started here.

## Read first

- `docs/plans/2026-07-24-gdpr-erasure.md` (governing plan; the E1 bullet defines this slice's exact semantics)
- `packages/app/src/lib/flows/companies.ts` + `provision.ts` (flow + transaction patterns)
- `packages/app/src/app/api/orgs/**` (session + CSRF route patterns to mirror)
- `packages/app/src/app/settings/companies/` (UI to extend)
- `packages/app/src/app/admin/orgs/` actions + `src/lib/admin-auth.ts` (admin gate pattern: page AND every action)
- `packages/app/src/app/api/admin/machine/memberships/route.ts` (machine API patterns)
- `packages/shared/src/types.ts` (OutboxEventType; membership events)

## Definition of done

1. **Flow** `transferOwnership(sql, { scope_type: 'tenant' | 'tenant_group', scope_id, from_user_id, to_user_id, actor })`, one transaction, atomic swap: `to_user` must already hold a live membership at that scope (else 400), gains role `owner`; `from_user` (must currently be an owner, else 403) demotes to `admin`. Personal tenant_groups (`is_personal = TRUE`) are NOT transferable (400 with a clear code). Emits the existing membership outbox events for both role changes (so OpenFGA tuples update through the normal sync) plus an audit entry naming actor, scope, from, to.
2. **Self-serve route** `POST /api/orgs/[tenantId]/transfer-ownership` (session + CSRF, mirroring existing org routes): caller must be an owner of that tenant; body `{ to_user_id, csrf_token }`. Explicit error codes (400 non-member target / personal scope, 401, 403 non-owner, 404 unknown-or-foreign tenant, no existence leak).
3. **Settings UI**: in `settings/companies`, an owner sees a "Transfer ownership" action per company: pick an existing member, typed company-name confirmation, clear warning that they will become an admin. Errors surfaced; no dead ends.
4. **Admin console**: a transfer action on the org page (both tenant and non-personal tenant_group scopes), gated by `requirePlatformAdminFromCookies` on the page AND the action, with a non-admin 403 test for each.
5. **Machine API** `POST /api/admin/machine/ownership-transfer` (auth-brain ADMIN_API_KEY + `actor_email`): same flow, scope_type + scope_id + to_user_email resolution consistent with the memberships route.
6. **Tests** (vitest, existing patterns; Docker-probe pattern for DB specs):
   - owner transfers to member: roles swap atomically; outbox events + audit written
   - non-owner caller 403; target not a member 400; personal tenant_group 400; unknown/foreign scope 404; unauthenticated 401; CSRF rejected
   - co-owner scenario: transfer from one of two owners demotes only the caller (the other owner is untouched)
   - revision path: transfer A -> B then B -> A restores the original state exactly (roles, no duplicate memberships)
   - admin console actions: non-admin 403 on page and action; machine API: bad key rejected
7. `pnpm test && pnpm typecheck && pnpm lint` green. Single conventional commit explaining the WHY (legal unblock path for GDPR erasure).

## Constraints

- Stay in this worktree. Do not push.
- Do NOT begin the erasure state machine, deletion surfaces, or webhook fan-out (slice E2).
- Do not change membership uniqueness, signup, invitations, or the OpenFGA model; the transfer rides existing membership event kinds.
- Fail closed; never log tokens/cookies/sessions.
- No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.
