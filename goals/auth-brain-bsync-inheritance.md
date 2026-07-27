---
task: auth-brain-bsync-inheritance
spec: docs/plans/2026-07-24-authz-hardening.md (decisions 1+2) + docs/internal/fga-authoritative-tradeoffs.html
depends_on: [auth-brain-workspace-key-grants]
shared_state: [migrations]
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: B-sync write path + role inheritance in the FGA model (pre-launch gate item 4)

This is the standing, already-decided shape. Do not re-litigate it. The binding
decisions are `docs/plans/2026-07-24-authz-hardening.md` decisions 1 and 2, and
the trade-off record `docs/internal/fga-authoritative-tradeoffs.html`.

## Current state (verified 2026-07-27)

- `packages/app/src/lib/openfga/schema.json` (schema 1.1) ALREADY contains
  userset rewrites. An earlier draft of this goal wrongly called it flat; that
  was an operator error from listing relation names without their definitions.
  The ACTUAL current definitions are:
  - `tenant_group.parent`, `tenant_group.owner`: direct only
  - `tenant_group.admin` = this OR owner OR (parent's admin)
  - `tenant_group.member` = this OR admin
  - `tenant.group`, `tenant.owner`: direct only
  - `tenant.admin` = this OR owner OR (group's admin)
  - `tenant.billing_admin` = this OR owner
  - `tenant.member` = this OR admin
  - `workspace.tenant`: direct only
  - `workspace.admin` = this OR (tenant's OWNER)
  - `workspace.member` = this OR admin OR (tenant's MEMBER)
  - `workspace.viewer` = this OR member
  - `platform.admin`: direct only; `platform.auditor` = this OR admin
  Verify this yourself before changing anything; do not trust this summary
  blindly.
- Tuple writes are ASYNC: mutations call `enqueueOutboxEvent(tx, {...})`
  (`packages/app/src/lib/outbox.ts`) and `packages/app/src/lib/openfga/sync-worker.ts`
  (consumer `openfga-sync`) drains them into `writeAndDeleteTuples`
  (`packages/app/src/lib/openfga/client.ts`). The kinds it handles are:
  `tenant_group.created`, `tenant_group_membership.granted|revoked`,
  `tenant.created`, `tenant_membership.granted|revoked`, `workspace.created`,
  `workspace.moved`, `workspace_membership.granted|revoked`,
  `service_account.role_granted|revoked`, and the three `*.deleted` kinds.
- The model is uploaded by `packages/app/src/lib/openfga/push.ts`.

## Part 1: synchronous dual writes (B-sync)

Every membership/grant mutation must write Postgres AND its OpenFGA tuple in the
SAME request, failing LOUD if the tuple write fails. The async outbox path for
exactly the FGA kinds listed above is retired; the outbox itself STAYS for audit
and mail fan-out (erasure webhooks, invitations, etc.) and must keep working.

Requirements:

- A single choke point (a small module, e.g. `lib/authz-writes.ts`) that performs
  the Postgres write and the tuple write for one mutation. Every write path goes
  through it: the machine API routes under
  `packages/app/src/app/api/admin/machine/*` (memberships, app-grants,
  ownership-transfer, tenants, workspaces, orgs, service-accounts), invitation
  acceptance, and tenant/workspace/org creation (which imply an owner tuple).
- Ordering and failure semantics, stated explicitly in a comment and covered by
  tests: if the tuple write fails, the request fails and the Postgres work does
  not silently persist as an over-grant. Prefer doing the FGA write inside the
  Postgres transaction boundary such that a tuple failure rolls the transaction
  back. If a true two-phase guarantee is impossible, the safe direction is:
  never leave a GRANT in Postgres without its tuple (an over-grant is worse than
  a missing one), and never leave a REVOKE in Postgres with the tuple still live.
  Write down whichever guarantee you implement.
- Remove the retired kinds from `sync-worker.ts` deliberately: if a kind is no
  longer enqueued, the worker branch for it should be deleted (not left dead) OR
  kept only as a compatibility drain for rows enqueued before deploy. Choose one,
  say which, and make the code say why. Do NOT delete the worker wholesale: the
  outbox still carries non-FGA kinds.

## Part 2: reconciliation job

A job that diffs Postgres membership/grant state against FGA tuples and reports
mismatches LOUDLY. Reuse the alerting channel this repo already uses (find it;
do not invent a new one). Runnable on a schedule (the deploy runs an
`auth-brain-worker` container; wire it the same way the existing workers are
wired) and also runnable on demand. It must report, per mismatch: scope type,
scope id, subject id, role, and which side is missing. It must NOT auto-heal
silently by default: healing may exist behind an explicit flag, but the default
run is report-only, because a silent auto-heal can paper over a write-path bug.

## Part 3: inheritance in the FGA MODEL

The model is PARTLY there already, so this part is a set of precise DELTAS
against the definitions listed above, not a from-scratch encoding. Reconcile
`schema.json` to decision 1, then make `push.ts` publish the new model version.

**Delta 1 (a live over-grant, fix this first).** `workspace.member` currently
includes `(tenant's member)`. That is a downward cascade of plain `member`,
which decision 1 explicitly forbids: "a cascading `member` would silently make
every org member a member of every company and workspace beneath, which is
wrong... being in a company or workspace always requires a direct membership
there." Today every company member is automatically a member of EVERY workspace
in that company. Remove the `tenant's member` arm from `workspace.member`.
Keep `this OR admin` (a workspace admin is still a member of that same
workspace: that is role hierarchy WITHIN one scope, not a cascade across tiers).

Removing this narrows real access, so it may drop people out of workspaces they
currently reach implicitly. Before/after, produce a count (and, if cheap, a
list) of (user, workspace) pairs that lose access, so the operator can seed
direct memberships where they were actually intended. Report it in your final
message. Do NOT auto-create those memberships.

**Delta 2.** `workspace.admin` currently inherits only from the tenant's OWNER.
Decision 1 says company `owner` AND `admin` both become effective `admin` on the
company's workspaces. Add the tenant's `admin` arm.

**Delta 3.** `tenant.owner` is direct-only, so an org owner currently becomes
tenant ADMIN (via `tenant.admin` <- group's admin <- group owner) but never
tenant OWNER. Decision 1 says org `owner` -> effective `owner` on child
companies. Add that arm to `tenant.owner`.

**Leave alone, and say why in a comment:** `tenant.member = this OR admin`,
`tenant_group.member = this OR admin`, `workspace.viewer = this OR member`,
`tenant.billing_admin = this OR owner`, `platform.auditor = this OR admin`.
These are same-scope role hierarchies (a higher role at a scope implies the
lower one AT THAT SAME SCOPE), not cross-tier cascades, so decision 1's
"member never cascades" rule does not touch them. `billing_admin` must not gain
any cross-tier arm.

Invariant to preserve throughout: direct role wins if higher; inheritance must
never LOWER an explicit direct role.

Model migration safety: uploading a new authorization model creates a new model
id. Make sure the client resolves the model id the same way after the change
(check how store id / model id are configured in `client.ts` and `push.ts`) and
that an old model id pinned in config does not silently keep serving the old
semantics. State in your final message how the new model gets adopted at deploy.

## Part 4: effective roles in the verify payloads

Session verify (`packages/app/src/app/api/sessions/verify/route.ts`) and api-key
verify (`packages/app/src/app/api/verify/api-key/route.ts`) must deliver
EFFECTIVE roles, each marked `direct` vs `inherited`.

- No materialized duplicate membership rows. Effective roles are computed at
  verify time from the FGA evaluation.
- The wire shape changes, so the shared package's zod schemas must change with
  it, and `packages/app/src/app/api/verify-wire-contract.spec.ts` must keep
  proving the real response parses with the PUBLISHED schemas.
- Keep it additive where possible so consumers that read the existing `role`
  field do not break in the same deploy. If you must change an existing field's
  meaning, say so loudly in your final message; the operator publishes
  shared/SDK bumps and updates consumers.
- Do NOT make any consuming app talk to FGA directly. Apps read only the verify
  payload. That is the whole point of decision 2.

## Part 5: UIs show direct vs inherited

Settings/companies member lists and the admin console member lists must show
whether a role is direct or inherited, because revocation semantics differ (an
inherited role cannot be revoked at the child; you change it at the source or set
a higher direct role). Keep the UI change small and legible; do not redesign
these pages.

## Part 6: revision-path tests (REQUIRED, non-negotiable)

Per `knowledge-base/standards/stateful-flow-testing.md`, forward-path tests are
not sufficient. Cover:

1. Forward: grant at org level, assert effective admin appears on child tenant
   and workspace, marked inherited.
2. Backtrack/revise: CHANGE the source role (org admin -> member, and org
   owner -> revoked) and assert every downstream effective role is invalidated;
   assert the counter-case that re-asserting the SAME role does not churn.
3. Direct-wins: a direct role higher than the inherited one survives; a direct
   role LOWER than the inherited one does not lower the effective role.
4. Never-cascade: `member` and `billing_admin` at a parent produce NO effective
   role on children, at every tier. Specifically assert the Delta 1 regression:
   a plain company `member` gets NO access to a workspace in that company
   without a direct workspace membership. Also assert the same-scope hierarchies
   that must SURVIVE (a workspace admin is still a workspace member; a tenant
   admin is still a tenant member).
5. Dual-write failure: a simulated FGA failure fails the request loudly and does
   not leave an over-grant in Postgres.
6. Reconciliation: a deliberately-introduced divergence is detected and reported.

Also add at least one test that exercises the REAL schema/wire boundary rather
than a mock (the repo already has `verify-wire-contract.spec.ts`; extend it).
Mock-only coverage is exactly how the workspace-grant bug shipped: real
auth-brain never sent `app_grants` on a workspace scope while storage-brain's
tests mocked one that did.

## Definition of done

- The verify chain in this goal's frontmatter exits 0.
- `pnpm --filter @auth-brain/app test:integration` (needs
  `docker compose up -d postgres openfga`) passes; run it if docker is available,
  and say explicitly in your final message if it was not.
- All six test groups above exist and pass.
- Your final message states: the dual-write guarantee you implemented, how the
  new FGA model version is adopted at deploy, and whether the shared/SDK wire
  shape changed (the operator publishes the bumps and updates consumers).

## Constraints

- This is the live identity service for the whole suite. Prefer the smallest
  correct diff per part; do not refactor adjacent code.
- Do NOT touch: MFA/session hardening, the GDPR erasure wave, the suite-apps
  registry entries, or storage-brain.
- Do NOT weaken or delete tests to make a gate green. If a gate legitimately
  needs a test changed, change it deliberately and say why.
- If Part 1's transactional guarantee turns out to require a design decision the
  spec does not settle, STOP and escalate rather than guessing.
