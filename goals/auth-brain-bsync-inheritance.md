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

- `packages/app/src/lib/openfga/schema.json` is a FLAT model, schema 1.1:
  - `tenant_group`: parent, owner, admin, member
  - `tenant`: group, owner, admin, billing_admin, member
  - `workspace`: tenant, admin, member, viewer
  - `platform`: admin, auditor
  There are NO userset rewrites, so no role inherits anything today.
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

Encode decision 1 as userset rewrites in `schema.json`, then make `push.ts`
publish the new model version:

- `tenant_group.owner` -> effective `owner` on child `tenant`s;
  `tenant_group.admin` -> effective `admin` on child `tenant`s. (The `tenant`
  type already has a `group` relation to hang this on.)
- `tenant.owner` / `tenant.admin` -> effective `admin` on that tenant's
  `workspace`s (workspaces have no owner tier). The `workspace` type already has
  a `tenant` relation.
- `member` NEVER cascades at any tier. `billing_admin` NEVER cascades
  (tenant-only semantics). `viewer` does not cascade.
- Direct role wins if higher; inheritance must never LOWER an explicit direct
  role.

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
   role on children, at every tier.
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
