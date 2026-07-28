---
task: auth-brain-company-move-api
spec: mirrors the workspace-move half of PATCH /api/admin/machine/workspaces (auth-brain#65)
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: let the machine API MOVE a company between orgs

`PATCH /api/admin/machine/workspaces` can move a workspace to another tenant
(and rewrites the FGA parent tuple as part of it). The tenant equivalent does
NOT exist: `PATCH /api/admin/machine/tenants` only renames (name/slug), so a
company cannot be moved from one `tenant_group` to another except by raw SQL.

Raw SQL is the wrong answer here and we have same-day evidence: two production
incidents on 2026-07-27/28 traced back to SQL-created state with no audit row
and no FGA tuple (a company that appeared with no creation event, and a
workspace-scoped key swap nobody could trace). Moving a company by hand would
also leave the `tenant_group:<old> group tenant:<T>` tuple stale until someone
ran reconciliation.

Operator need driving this: consolidating `lumitra-core` (and future companies)
under the `marlinjai` org so one org is the umbrella.

## What to build

Extend `PATCH /api/admin/machine/tenants` with an optional `group_id` (the
destination org). Semantics mirror the workspace-move path in
`packages/app/src/app/api/admin/machine/workspaces/route.ts` and its underlying
flow (find it; `scope-mutation.ts` holds `updateWorkspaceAsAdmin`):

- `group_id` alone moves; `name`/`slug` alone rename; together they do both in
  ONE transaction, exactly like the workspace endpoint.
- The destination org must exist and be live, else 404.
- The tenant's slug must remain unique where the schema requires it. Check the
  actual constraint before assuming: if company slugs are globally unique the
  move cannot collide, but if they are unique per group, a landing collision is
  a 409 (same shape the workspace endpoint returns).
- A no-op move (already in that group) is allowed and returns success.
- Reserved-slug validation on rename stays exactly as it is.

**The FGA side is the point.** The structural tuple `tenant_group:<G> group
tenant:<T>` must be rewritten in the SAME transaction: delete the old parent
edge, write the new one, via the synchronous choke point
`lib/openfga/authz-writes.ts` (B-sync, shipped in #69). Do not enqueue it for
the async worker and do not leave it to reconciliation. After a move,
`openfga:reconcile` must report ZERO findings without healing.

Emit an audit row and an outbox event for the move, attributed to
`actor_email`, so the change is traceable. Follow whatever the workspace move
emits.

## Why this matters beyond convenience (state it in a comment)

Under the inheritance model shipped in #69, an org's `owner`/`admin` cascade
DOWN to its child companies. Moving a company between orgs therefore CHANGES WHO
HAS EFFECTIVE OWNER/ADMIN ON IT. That is a real authorization change, not
bookkeeping, which is exactly why it needs an audited, tuple-correct endpoint
rather than an UPDATE statement.

## Tests (required)

- Move a company to another org: `group_id` updated, old parent tuple GONE, new
  parent tuple PRESENT (assert both sides, not just the write).
- Move + rename in one call behaves atomically; a failure leaves neither applied.
- Unknown destination org -> 404. Slug collision (if the constraint allows one)
  -> 409. No-op move -> success.
- Rename-only still works exactly as before (regression).
- Inheritance follows the move: a user who is owner of the DESTINATION org gains
  effective owner on the moved company, and an owner of the SOURCE org no longer
  does. Use the real OpenFGA integration harness
  (`tests/integration/inheritance-openfga.spec.ts` is the template) — the
  in-memory mock cannot evaluate userset rewrites.

## Definition of done

- Verify chain in the frontmatter exits 0.
- Integration suite if docker is available; say so explicitly if not (CI gates).
- Final message notes any shared/SDK bump (probably none: this is a request-body
  addition on an admin route, not a wire-shape change for consumers).

## Constraints

- Live identity service: smallest correct diff.
- Do NOT change workspace move, tenant deletion, or the inheritance model.
- Do NOT add a company-move to any human console UI in this slice; machine API only.
