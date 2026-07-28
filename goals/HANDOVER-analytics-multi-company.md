# HANDOVER: make Analytics a proper multi-company citizen (SSO is done; the switcher is half-built)

You are the OPERATOR (Claude Code, `autonomous-orchestration` skill, agent teams).
Written 2026-07-28 by the session that shipped the B-sync authz wave. Read the
memory files `authz-decisions-prelaunch-gate.md` and
`reference_authz_bsync_live.md` first.

## Read this before planning: three assumptions that are WRONG

1. **"Analytics needs SSO like Studio."** It already has it.
   `packages/dashboard/src/middleware.ts:17-18` redirects unauthenticated page
   navigations to `${AUTH_BRAIN_URL}/login`, exactly like Studio's
   `src/middleware.ts`. Both ride the shared `lumitra_session` cookie. There is
   also a `/request-access` page for the app-grant door. **Do not rebuild auth.**

2. **"Copy Studio's company switcher."** Studio does NOT have one. Its
   middleware gates on membership of a single Studio workspace. Neither app has
   a scope switcher, so this is the FIRST one and it should be built at the
   platform level, not twice in two apps.

3. **"Analytics still talks to OpenFGA."** Almost gone. `openfga-direct.ts` was
   deleted (analytics-platform#38); project visibility now derives from the
   verify payload's `effective_roles`. ONE `can()` survives on purpose, for
   local CLI account keys, documented at
   `packages/dashboard/src/lib/auth-brain.ts:16-28`. Leave it unless you are
   explicitly doing the account-key migration (see "Deliberately out of scope").

## The actual problem: analytics is structurally single-company

Analytics assumes exactly ONE company exists, in several places:

- `packages/dashboard/src/lib/workspace-provisioning.ts:16-23` reads
  `AUTH_BRAIN_TENANT_SLUG` / `AUTH_BRAIN_TENANT_NAME` / `AUTH_BRAIN_GROUP_ID`
  from env, with defaults that used to be `lumitra-analytics` under the Lumitra
  org.
- `ensureAnalyticsTenant()` (same file, ~line 100) POSTs that company to
  auth-brain's machine `/tenants` on EVERY boot, swallowing "already exists".
- `provisionProjectWorkspace()` creates every project's workspace under that one
  `TENANT_SLUG`.
- `projects` (migration 001) has **no company column at all**. `workspace_id`
  was added in migration 014. A project's company is implicit: whatever company
  owns its workspace.

**Two production incidents on 2026-07-28 came from exactly this**, so treat it
as demonstrated, not theoretical:
- A phantom "Lumitra Analytics" COMPANY kept reappearing (created 2 seconds
  after each analytics boot). Deleting it did nothing; the next deploy remade
  it. Fixed for now by pointing the env at the real `lumitra-core` company.
- `lola-web` and `lola-landing` project workspaces sat under the **Lumitra**
  company when they belong to **Lola Stories**, purely because analytics puts
  every project under its one configured company. Moved by hand.

Both will recur for any new project until the model changes.

## The switcher is HALF-BUILT ALREADY (the key finding)

Do not design this from scratch. auth-brain already models active scope:

- `packages/app/migrations/004_sessions.sql:4-5` — `sessions.active_tenant_id`
  and `sessions.active_workspace_id` columns.
- `SessionVerifyResponse` carries `active_tenant` / `active_workspace` objects
  (`packages/shared/src/types.ts:153-154`), assembled in
  `packages/app/src/app/api/sessions/verify/route.ts:62`.
- `setActiveContext(sql, sessionId, tenantId, workspaceId)` exists at
  `packages/app/src/lib/db/repositories/sessions.ts:94` — and has **ZERO
  callers**. Nothing exposes it.

So the platform work is: expose a "switch active scope" endpoint that validates
the user actually holds a role on the target scope, calls `setActiveContext`,
and lets every suite app read `active_tenant` from the payload it already
receives. That is a small auth-brain slice, and it makes the switcher available
to Studio and Receipts for free.

## Decisions needed from Marlin BEFORE building (do not guess these)

1. **What does a "project" belong to?** Options: (a) a project belongs to a
   COMPANY, and its workspace is created under that company; (b) a project
   belongs to a WORKSPACE the user picks, which already implies a company.
   (b) is closer to the existing schema (`projects.workspace_id`), (a) reads
   more naturally to a user. This decides the creation UI and the data model.
2. **Does switching scope filter the project list, or is the list global?**
   i.e. is the switcher a FILTER (show projects in the active company) or a
   BOUNDARY (you cannot even see the others)? Fail-closed suggests boundary.
3. **Backfill:** every existing project sits under Lumitra. Do they get
   reassigned to real companies (Lola's projects to Lola Stories), and by what
   rule? Today's manual moves are the precedent.

## Suggested slices (dependency-ordered)

**S1 auth-brain: active-scope endpoint.** Expose the switcher primitive. Must
verify the caller actually holds a role on the target tenant/workspace (never
trust a client-supplied id), write via `setActiveContext`, and return the
updated payload shape. Add revision-path tests per
`knowledge-base/standards/stateful-flow-testing.md`: switch, switch back, switch
to a scope you lost access to (must fail closed), and resume after re-login.
Bump shared/SDK; the operator publishes.

**S2 analytics: project -> company binding.** Per decision 1. Add the column or
formalise the workspace link, make project CREATION take a target company/
workspace the user actually has rights on, and delete `ensureAnalyticsTenant()`
so analytics never provisions a company again. Analytics should CONSUME
companies, never create them.

**S3 analytics: the switcher UI + scoping.** Read `active_tenant` from the
verify payload, render the picker from the payload's companies, call S1's
endpoint. Apply decision 2 to the project list and every project-scoped route.

**S4 backfill.** Per decision 3, using the machine APIs — `PATCH
/api/admin/machine/workspaces` moves a workspace between companies and rewrites
the FGA parent tuple atomically (auth-brain#72 added the tenant equivalent). Do
NOT move things with raw SQL.

## Traps this session hit, do not relearn them

- **Pushing code does not change authorization.** Adopting a new OpenFGA model
  is MANUAL: `openfga:push`, then set `OPENFGA_AUTHORIZATION_MODEL_ID` in
  Infisical, then restart. Between merge and that flip, prod runs the OLD model.
- **Verify against the model the service actually queries**, not the repo's
  `schema.json`.
- **Raw SQL on identity data is how today's two incidents happened** (a company
  with no creation event; an untraceable key swap). Use the machine APIs; they
  emit audit + outbox rows and keep tuples correct.
- **Deleting a scope currently leaks its FGA tuple** until `openfga:reconcile
  -- --heal`. A fix is in flight (`auth-brain-delete-tuple-sync`); check whether
  it landed.
- **Analytics CI builds first**; a stray non-route export in a Next route file
  has broken that build before. Studio has NO CI verify workflow at all, so
  local verification is the only gate there.
- The reconcile CLI needs the app's injected env, which `docker exec` does not
  inherit: read it from `/proc/<pid>/environ` of the node process and pass with
  `-e`.

## Deliberately out of scope

- The surviving `can()` for CLI account keys. Those are developer credentials
  (`ap_account_` prefix, minted via the `cli_device_codes` device flow), not
  customer-facing ingest keys. Migrating them to auth-brain service accounts is
  a SEMANTIC change (an account key means "act as user X"; a service account is
  a machine bound to a scope) and would force every CLI user to re-authenticate.
  Marlin's standing call: leave it until analytics gains a non-human consumer.

## Key ids

Orgs: `marlinjai` `019f6a90-8b69-7d7f-a8fe-268b62ae1cc7` (umbrella: Lumitra +
marlinjai + Whiz-Art Media), `Lola Stories` `019f6a89-ea38-7f0e-bbe7-544652b65f56`,
`sharondisalvo` (personal, Opuntia + Return Hypnosis). Companies: `lumitra-core`
`019ec2f2-f19e-70f4-a889-8afb34c314ca`, `lola-stories`
`019f6a89-ea4a-75d4-90ff-4e809491647e`. Infisical: auth-brain
`97c4971e-78c1-4adf-83e1-6c0b5f13375c`, analytics workspace resolves by name
"Analytics Platform". auth-brain app container prefix
`h10iicx7b1g7c5dj9z69z4f2`, analytics `u30x30hokl4flljrmvywy5t8`, auth-brain DB
container `gzcpriw2sbpsuwka4spb788x`, shared-server-I `157.90.119.98`.
