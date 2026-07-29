---
task: analytics-projects-belong-to-companies
spec: orchestrator goals/HANDOVER-analytics-multi-company.md slice S2 (decision 1, settled 2026-07-29)
shared_state: [migrations, lockfile]
verify: pnpm build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: an analytics project belongs to a COMPANY, not to a workspace

Marlin settled this on 2026-07-29 and it is not reopenable in this slice.

Analytics currently mints one auth-brain **workspace per project** and uses
workspace membership as a per-project ACL. That was never a design choice — it
was a workaround, because a workspace was the smallest scope auth-brain offered.
It is the wrong layer: it leaks an app's domain object (a tracked website) into
the identity service, it does not scale (50 sites = 50 workspaces in every user's
verify payload on every request), and no sibling app does it (Studio does not do
this per brand; receipts does not do it per client).

**Target model:** a project belongs to a **company** (auth-brain `tenant` uuid).
Access is company membership. A role matrix inside analytics decides what
viewer/member/admin may do to a project.

**Accepted cost (Marlin's explicit call):** per-project granularity is dropped.
Anyone who can see a company's analytics sees all of that company's projects.
Nobody uses the granularity today. Do NOT try to preserve it.

## Verified ground truth (I checked prod directly — trust this over any doc)

The `projects` table in production holds **exactly two rows**:

| project id | name | domain | workspace_id |
|---|---|---|---|
| `6e00471d-8f15-4a0d-b341-02766fa0712a` | `lola-landing` | `lolastories.com` | `019ee142-44af-786d-9366-a705b7607f86` |
| `8f469eec-66eb-4bf6-96e7-978fd775fc5d` | `lola-web` | `app.lolastories.com` | `019ee142-453c-702c-9e6e-cba872eadcca` |

Both must be backfilled to the **Lola Stories** company
`019f6a89-ea4a-75d4-90ff-4e809491647e`. There is nothing else to reassign.

## CORRECTION TO THE HANDOVER

The handover points at `lumitra-studio/src/lib/auth/roleMatrix.ts` as the
reference. **That file does not exist.** Studio's real shape (which IS worth
copying) is three modules in `src/lib/auth/`:

- `permissions.ts` — the action vocabulary: a `satisfies Record<string, {requires: PermissionRequirement, description: string}>`
  map from an action name to a `<scope>.<role>` requirement. `PermissionRequirement`
  is a published type from `@marlinjai/auth-brain-sdk`. The `satisfies` clause is
  what makes a typo like `tenant.editor` a compile error.
- `can.ts` — the route-boundary guard (`guardMutation`) returning a ready-to-send
  denial.
- `scope.ts` — caller resolution plus the data-layer scoping helpers
  (`tenantWhere`, `canSee`, `writeTenantId`).

Read all three before writing yours. Two Studio decisions to carry over
explicitly, both named in the handover:
- **`billing_admin` stays OFF the general ladder.** It authorises billing only
  and must never satisfy a viewer/member/admin check.
- **The `direct` vs `inherited` marker is IGNORED for gating.** An inherited
  admin IS an admin. `packages/dashboard/src/lib/project-access.ts` already
  documents and implements this correctly for workspaces — preserve that
  reasoning when you move to companies.

## What to build

### 1. Migration: `company_id` on `projects`

Next number is `018-postgres.sql` in `packages/shared/src/migrations/`
(017 is the current highest). Follow the existing file conventions.

- Add `company_id UUID` (additive).
- Backfill the two rows above, keyed on `workspace_id` (their ids are stable and
  exact). Do NOT key the backfill on `name` or `domain`.
- Add an index on `company_id` (mirroring `idx_projects_workspace` from 014).
- Then `SET NOT NULL`, guarded exactly like migration 014 does it: if any row
  still has a NULL `company_id`, `RAISE EXCEPTION` with an actionable message
  rather than silently leaving unreachable projects. Read 014 and copy its shape.
- **Leave `projects.workspace_id` in place and untouched.** Dropping it is a
  separate follow-up migration once nothing reads it. Do not do both in one step.

### 2. Delete the provisioning path — analytics must never write to auth-brain again

Analytics is an APP entitled via `app_grants`. It **consumes** companies; it does
not create them. This code auto-created a phantom company on every single boot
and caused a real production mess.

Delete: `ensureAnalyticsTenant`, `provisionProjectWorkspace`,
`grantWorkspaceMember` (`packages/dashboard/src/lib/workspace-provisioning.ts`),
and `provisionMissingWorkspaces` (`packages/dashboard/src/lib/provision-workspaces.ts`),
plus the boot-time call in `packages/dashboard/src/instrumentation.ts`.

**Keep `runMigrations()` in `instrumentation.ts`** — only the provisioning step
goes. Note the existing comment there claims provisioning must run first so
migration 014 can succeed; that ordering constraint dies with the provisioning
step, so update the comment to match reality rather than leaving it lying.

Remove the now-dead env plumbing with it: `AUTH_BRAIN_TENANT_SLUG`,
`AUTH_BRAIN_TENANT_NAME`, `AUTH_BRAIN_GROUP_ID`, and `AUTH_BRAIN_OWNER_EMAIL`
where it exists only to serve provisioning. Sweep every occurrence (code,
Dockerfile/entrypoint, CI, `.env.example`, docs). `AUTH_BRAIN_URL` and
`AUTH_BRAIN_ADMIN_KEY` may still be needed by other code — check before removing.

The one-shot cutover script `packages/dashboard/scripts/migrate-to-auth-brain.mjs`
is historical. Deleting it is in scope and preferred (git history keeps it); if
you keep it, do not leave it importing deleted modules.

### 3. The analytics permission matrix (new module)

Create the analytics equivalent of Studio's `permissions.ts`. The auth-brain
**tenant** role ladder is `owner | admin | billing_admin | member | viewer`
(viewer is the lowest rung, read-only, shipped in auth-brain#73).

Unlike Studio (whose every action is `tenant.member`), analytics has genuinely
distinct tiers. Map every action analytics performs onto a minimum company role.
Derive the action list from the real routes; the shape should be roughly:

- **read** (`tenant.viewer`): stats, funnels, heatmaps, session replay, reading
  experiments/flags, exports.
- **write** (`tenant.member`): create/edit/start/stop experiments, flags,
  funnels, test links.
- **admin** (`tenant.admin`): project settings, project + account API keys,
  the destructive project reset, project creation and deletion.

Use judgement on each route; state your final mapping in your report. What is
NOT negotiable: destructive and credential-minting actions are `tenant.admin`,
and `billing_admin` never satisfies any of them.

### 4. Swap the decision from workspace to company

- `packages/dashboard/src/lib/project-access.ts`: add the company equivalent of
  `hasWorkspaceAccess`, reading `effective_roles.tenants` and honouring the
  ladder above. Keep its excellent fail-closed doc comment and its "ignore the
  direct/inherited marker" reasoning.
- `packages/dashboard/src/lib/auth-check.ts`: `lookupWorkspaceId` becomes a
  company lookup; `checkWorkspaceAccessForSession` decides on company role.
- `packages/dashboard/src/app/api/projects/route.ts:46`: replace
  `hasWorkspaceAccess(..., p.workspace_id, 'workspace.viewer')` with the company
  check.
- `packages/dashboard/src/lib/auth-api.ts` is the single seam
  (`authenticateRequest`) every project-scoped route funnels through. Change it
  there once rather than at ~30 call sites. `resolveRequiredRole` /
  `mapToWorkspaceRole` need to become company-role aware — and note the existing
  `'owner' | 'admin' -> workspace.admin` collapse must not silently let
  `billing_admin` through when you re-point it at the tenant ladder.

A project whose `company_id` is NULL or unknown is **inaccessible** (deny), the
same way a NULL `workspace_id` is treated today. Never fall open.

### 5. Project creation takes a target company

`POST /api/projects` must take the target company and **validate the caller
actually holds a role on it against the verify payload**. Never trust the request
body. Creation is a `tenant.admin` action per the matrix.

The current flow resolves an `ownerEmail` purely to provision a workspace; that
whole branch dies with the provisioning code. An account-key (CLI) caller has no
verify payload — see below.

### 6. The account-key wrinkle (read before touching auth)

`checkAccountKeyProjectAccess` is the ONE surviving direct `can()` in analytics.
Account keys are developer CLI credentials (`ap_account_` prefix) that produce no
verify payload at all, so there is nothing to read roles from.

It must become "does this user hold a role on the project's **COMPANY**" instead
of "on the project's workspace" — i.e. a `can()` against the `tenant` type rather
than `workspace`. Check the SDK's `can()` / `ResourceHandle` actually accepts a
tenant-typed resource before assuming it.

What is **NOT acceptable**: silently dropping the check, or failing open. Keep it
fail-closed, and keep the comment explaining why this FGA survivor exists.

If the SDK cannot express a tenant-scoped `can()`, STOP and escalate rather than
inventing a local rule — a silent semantic change here is an access-control bug.

## Tests (required)

- The company check: allowed and denied cases per tier, asserted against the real
  published `EffectiveRoles` shape (not a hand-written mock). `packages/dashboard/src/__tests__/project-access.test.ts`
  already has a "against the REAL published verify schema" block — extend that
  pattern, do not regress it.
- **`billing_admin` is denied** at viewer, member and admin tiers. Assert
  explicitly; this is the easiest thing to get wrong.
- **Inherited parity**: an inherited company admin is an admin.
- **Fail-closed**: null payload, unknown company, project with NULL `company_id`,
  verify failure/timeout — all deny.
- **No cross-company read**: a user in company A cannot see a project in company B
  through the list endpoint or the seam.
- Project creation: rejects a company the caller holds no role on; rejects a
  body-supplied company the payload does not confirm.
- Account-key path: allowed + denied against the company, and fail-closed on FGA
  error.
- The migration: assert both known rows land on the Lola Stories company.

## Definition of done

- The frontmatter verify chain exits 0. **Analytics CI BUILDS FIRST**
  (`build -> typecheck -> lint -> test`) — mirror that order exactly. A stray
  non-route export in a Next route file has broken this build before.
- If you change any dependency range, **COMMIT THE UPDATED LOCKFILE**. Workers
  forgetting `pnpm-lock.yaml` on a dependency bump is a known recurring failure
  in this repo. Current pins: `@marlinjai/auth-brain-sdk` `^1.4.0`,
  `@marlinjai/auth-brain-shared` `^1.5.0`. Published today: shared `1.6.0`,
  sdk `1.4.0`. Verify the installed version really exposes what you use.
- Your final message states: the full action -> minimum-company-role matrix you
  landed, how you handled the account-key `can()`, and every env var you removed.

## Constraints

- Do NOT touch auth-brain in this slice.
- Do NOT build the scope-switcher UI or the active-company boundary — that is the
  next slice (S3) and it builds on this one. Stay out of it.
- Do NOT drop `projects.workspace_id`.
- Do NOT delete the two auth-brain workspaces (a later operator step does that).
- Do NOT weaken or delete existing tests to make the suite green.
- Public ingest/collect endpoints (`/api/collect`, `/api/ingest`) authenticate by
  site key and must NOT be gated by company membership. Do not touch them.
