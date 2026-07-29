---
task: auth-brain-active-scope-endpoint
spec: orchestrator goals/HANDOVER-analytics-multi-company.md slice S1 (Marlin authorised the whole chain 2026-07-29)
shared_state: [migrations]
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: make the active-scope (company switcher) endpoint correct and fail-closed

The suite is getting a company scope switcher. Marlin decided on 2026-07-29 that
**the active company is an access BOUNDARY, not a view preference**: a resource
outside the active company must 403/404 on every entry point, and the active
scope must be re-validated against the user's LIVE roles on every request, so a
revoked role fails closed immediately instead of waiting for a new session.

This slice makes auth-brain deliver that guarantee. Studio and Receipts get the
capability for free.

## CORRECTION TO THE HANDOVER — read this first

The handover says the switcher endpoint "is missing" and that `setActiveContext`
has "ZERO callers". **That is wrong.** Verify it yourself, then work from reality:

- `packages/app/src/app/api/sessions/active-context/route.ts` **already exists**
  (shipped in the v1 PR #3) and already calls `setActiveContext`.
- `activeContextBodySchema` already exists (`packages/shared/src/schemas.ts:139`).
- `setActiveContext` is at `packages/app/src/lib/db/repositories/sessions.ts:94`.
- `sessions.active_tenant_id` / `active_workspace_id` already exist (migration
  `004_sessions.sql`). **You almost certainly need NO new migration.** If you
  think you do, say why in your final message.

So this is NOT "build an endpoint". It is **fix the endpoint that exists, close
the read hole, and give the whole thing tests it has never had.**

## The four defects to fix

### 1. The write gate validates DIRECT membership only — it now under-grants

Today the route checks raw membership rows:

```ts
const [m] = await sql`SELECT 1 FROM tenant_memberships WHERE user_id = ${session.user_id} AND tenant_id = ${body.tenant_id} AND deleted_at IS NULL`;
if (!m) return NextResponse.json({ error: { code: 'forbidden' } }, { status: 403 });
```

Since role inheritance shipped (#69), that is **wrong**: an org owner/admin holds
an EFFECTIVE owner/admin on child companies with **no direct membership row**.
Such a user is legitimately entitled to that company and today gets a false 403 —
they could never switch into a company they actually control.

Fix: validate the target against **effective** roles, not direct rows. The
canonical primitives are in `packages/app/src/lib/openfga/client.ts`:
`check(user, relation, object)` (cheapest — one round trip per target) and
`listObjects`. `packages/app/src/lib/authz/effective-roles.ts` is the reference
for how the rest of the codebase reasons about effective vs direct.

- Holding **any** role at the target scope is enough to make it your active
  scope. Switching scope is not itself a privileged action; what you may DO in
  that scope is decided per-app by that app's role matrix.
- **Fail closed on FGA error.** If OpenFGA is unreachable, do NOT fall back to
  "allow". Falling back to the direct-membership check is acceptable (it can only
  under-grant, never over-grant); a hard 503 is also acceptable. Choose one,
  comment WHY. Never allow-on-error.
- Unauthorised target stays a **403**, never a silent no-op.
- Keep validating `workspace_id` too, with the same effective-role treatment.

### 2. The verify read hole — this is the heart of the slice

`packages/app/src/app/api/sessions/verify/route.ts:62`:

```ts
const active_tenant = session.active_tenant_id ? await findTenantById(sql, session.active_tenant_id) : null;
const active_workspace = session.active_workspace_id ? await findWorkspaceById(sql, session.active_workspace_id) : null;
```

This resolves the stored id **without re-checking the user still holds a role
there**. A user whose role was revoked keeps reporting their old active scope
forever. That single line is what makes decision 2's "re-validated per request"
guarantee false today.

Fix: an active scope the user no longer holds must resolve to `null` on read,
**and be cleared** from the session row so the state converges instead of
silently re-failing every request. `effective_roles` is already computed a few
lines above in the same handler — reuse it, do not add another FGA round trip.

Apply the identical rule to `active_workspace`.

Same fail-closed discipline: when effective roles are degraded (the existing
`effectiveRolesOrDirect` fallback sets `degraded: true`), do **not** clear the
stored scope on the strength of a degraded read — a transient FGA outage must not
wipe every user's active scope. Report `null` for that request (fail closed on
the READ) but leave the stored column alone. Get this distinction right and say
in your final message how you handled it.

### 3. No default when nothing is set

Rule, exactly as decided:
- user holds exactly **one** company -> default the active scope to it;
- otherwise -> leave `null` and let the app require an explicit pick.

Never silently pick the first of several. Whether you materialise the default
into the session row or compute it per-request is your call — but a user who
gains a second company must stop being silently defaulted. State which you chose.

### 4. No tests at all

There is currently **no spec file anywhere** for `active-context`. This endpoint
is about to become an access boundary for the whole suite. It needs real
coverage (see Tests below).

## Secondary hardening: Origin check, and NOT a body CSRF token

The route is a cookie-authenticated state-changing POST with no CSRF defence.
Note the constraint before you "fix" that:

- the session cookie is domain-scoped to the whole suite
  (`domain: env.SESSION_COOKIE_DOMAIN`, `sameSite: 'lax'`);
- the CSRF cookie set in `packages/app/src/middleware.ts` is **host-only**
  (no `domain`), so it exists on auth.lumitra.co and nowhere else;
- auth-brain serves **no CORS headers at all**.

Therefore analytics (a different origin) can never read auth-brain's CSRF cookie
and will call this endpoint **server-to-server**, forwarding the session cookie.

**Do NOT add a `csrf_token` field to `activeContextBodySchema`.** It would be
unobtainable by the very caller this slice exists to serve, and would break S3.

`sameSite: 'lax'` already blocks cross-SITE POSTs. Add an **Origin allowlist**
check for the same-site residual: reject a browser POST whose `Origin` is present
and is not a known suite origin; allow a request with no `Origin` (server-to-
server). `packages/app/src/app/admin/users/actions.ts:26` has an origin-check
precedent. Keep it small, and comment why body-CSRF was rejected so the next
person does not "fix" it back.

## Tests (required)

Follow `knowledge-base/standards/stateful-flow-testing.md` — this is a stateful
flow and forward-only coverage is incomplete by definition. Cover:

- **Forward**: switch to a company you hold -> verify reports it.
- **Inherited entitlement**: an org owner with NO direct company membership row
  CAN switch into that child company (this is the regression the current code
  has). Use the real OpenFGA harness for this one; the in-memory mock cannot
  evaluate userset rewrites — copy the setup from
  `packages/app/tests/integration/inheritance-openfga.spec.ts`.
- **Unauthorised target**: 403, and the stored scope is unchanged.
- **Backtrack / switch back**: A -> B -> A converges, no stale state.
- **Revocation (the boundary guarantee)**: set active scope, revoke the role,
  then verify -> `active_tenant` is `null` AND the column was cleared. Assert
  both. This must NOT require a new session.
- **Degraded FGA on read**: verify reports `null` but does NOT clear the stored
  column.
- **Resume after re-login**: a new session for the same user starts with the
  documented default, not with the previous session's scope leaking in.
- **The no-active-scope default**: exactly-one-company defaults; two companies
  leave `null`.
- **Workspace parity**: the same rules hold for `active_workspace`.

## Definition of done

- The frontmatter verify chain exits 0. It mirrors CI (`.github/workflows/ci.yml`)
  minus the integration step, which needs a live Postgres service.
- **Also run the integration suite** (`pnpm --filter @auth-brain/app test:integration`,
  needs `DATABASE_URL` and docker; `docker compose up -d postgres openfga` is in
  the repo's dev script). If docker is unavailable in your environment, say so
  explicitly in your final message — CI gates it either way.
- Bump `@marlinjai/auth-brain-shared` and `@marlinjai/auth-brain-sdk` if and only
  if their public surface changed. **Do NOT publish** — the operator publishes.
  Current: shared `1.6.0` local/published, sdk `1.5.0` local but only `1.4.0`
  published. Report exactly what you bumped to.
- Final message states: the fail-closed choice you made for a degraded FGA read,
  the default-scope approach you chose, whether a migration was needed, and the
  version bumps.

## Constraints

- This is the **live central identity service** for the whole suite. Smallest
  correct diff. No refactors of adjacent code.
- Do NOT touch analytics, Studio, or storage-brain in this slice.
- Do NOT change the FGA model (`schema.json`). This slice needs no model change;
  if you believe it does, STOP and escalate rather than editing it — adopting a
  model is a manual production step and is not in scope here.
- Do NOT weaken or delete existing tests to make the suite green.
- Do NOT change the existing inheritance/cascade semantics from #69.
