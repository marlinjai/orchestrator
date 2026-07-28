---
task: auth-brain-delete-tuple-sync
spec: docs/plans/2026-07-24-authz-hardening.md decision 2 (B-sync); closes the delete-half gap left by #69
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: scope deletion must remove its tuples synchronously, like every other mutation

## The gap

B-sync (#69) made every membership/grant/structural WRITE synchronous through
`lib/openfga/authz-writes.ts`. Deletion was left behind: the sync-worker's
`tenant_group.deleted` / `tenant.deleted` / `workspace.deleted` cases are
explicit no-ops with a comment deferring cleanup to "a periodic GC job". So
deleting a scope soft-deletes it in Postgres and leaves its structural tuple
live in OpenFGA until somebody runs reconciliation with `--heal`.

This is not theoretical. It fired THREE times on 2026-07-28 in production:
deleting a stray company left `tenant_group:<G> group tenant:<T>` behind each
time, and each time reconciliation flagged it as an orphan and a manual heal
swept it. Between the delete and that heal, the two stores disagree — which is
exactly the drift window B-sync exists to eliminate.

Reconciliation should be the BACKSTOP that proves correctness, not the mechanism
that achieves it.

## What to change

Route scope deletion through the same synchronous choke point the writes use, so
the tuple deletes happen inside the deleting transaction and a tuple failure
rolls the whole delete back.

- `lib/flows/scope-deletion.ts` (the admin/console cascade: group, tenant,
  workspace) and `lib/flows/erasure-cascade.ts` (the GDPR path) are the two
  callers. Read both before changing either; the erasure path has its own
  ordering and MUST keep working exactly as it does today.
- The structural tuples to remove on delete mirror the ones written on create:
  `tenant_group:<G> group tenant:<T>` when a tenant dies,
  `tenant:<T> tenant workspace:<W>` when a workspace dies, and the
  `tenant_group:<parent> parent tenant_group:<child>` edge if a group dies.
  Membership tuples for the dying scope go too — check what the cascade already
  revokes via events so you do not double-handle what is already synchronous.
- Deleting a scope cascades to its children (a company takes its workspaces).
  The tuple cleanup must cover the whole cascade, not just the top scope, or you
  have simply moved the leak one level down.

Then deal with the sync-worker no-ops deliberately: either delete those branches
(if nothing enqueues them any more) or keep them as a compat drain for events
enqueued before this deploy. Choose one, say which, and make the comment tell
the truth — the current "a periodic GC job" comment is stale either way, because
that job now exists as reconciliation.

## Tests (required)

- Deleting a workspace removes its `tenant:<T> tenant workspace:<W>` tuple in the
  same transaction: assert the tuple is GONE immediately after the flow returns,
  with no reconciliation run in between.
- Deleting a company removes its own parent edge AND its workspaces' edges (the
  cascade case).
- A tuple-delete failure rolls the Postgres delete back: the scope is still live
  afterwards. This is the counterpart of the dual-write failure test from #69.
- Erasure cascade still behaves exactly as before (regression).
- After a delete, `reconcileOnce` reports ZERO findings WITHOUT healing. That
  assertion is the real proof the gap is closed; write it explicitly.
- Use the real OpenFGA integration harness for the tuple assertions
  (`tests/integration/inheritance-openfga.spec.ts` is the template).

## Definition of done

- Verify chain in the frontmatter exits 0.
- Integration suite if docker is available; say so explicitly if not (CI gates).
- Final message states what you did with the sync-worker no-op branches and why.

## Constraints

- Live identity service: smallest correct diff.
- Do NOT change the inheritance model, the verify payload, or the reconciliation
  job's own logic (it stays the backstop; healing stays opt-in).
- Do NOT make deletion hard-delete anything that is currently soft-deleted.
