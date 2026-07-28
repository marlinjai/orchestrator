---
task: authbrain-admin-api-completeness
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Two things, both consequences of the agent-first principle ("every operator action must be doable via the ADMIN_API_KEY machine surface"): (1) the admin machine API gains tenant RENAME and workspace MOVE/RENAME, which the operator currently cannot do without raw SQL (needed imminently for consolidating the historical Lumitra Core / Lumitra Analytics / Lumitra tenants into one company), and (2) the analytics door flips from open to app-grant (operator decision 2026-07-27, superseding the earlier open-door choice).

## Read first

- `packages/app/src/app/api/admin/machine/tenants/route.ts` + `workspaces/route.ts` (extend with PATCH; mirror their auth/validation/audit patterns)
- `packages/app/src/lib/flows/` (transactions, audit, outbox patterns), `packages/shared/src/types.ts` (OutboxEventType), `packages/shared/src/constants.ts` (RESERVED_TENANT_SLUGS)
- `packages/app/src/lib/openfga/sync-worker.ts` `tuplesFor`: CHECK whether `workspace.created` writes parent/relationship tuples. If workspace-to-tenant relations exist in the FGA model, a workspace MOVE must emit an event with an explicit `tuplesFor` case that rewrites them (silent default no-op would corrupt the graph); if no such tuples exist, document that in the event's comment.
- `packages/app/src/app/admin/orgs/` (console actions to extend), `src/lib/admin-auth.ts` (gate per page AND per action)
- `packages/app/src/lib/suite-apps.ts` (analytics entry + launcher tests)

## Definition of done

1. **`PATCH /api/admin/machine/tenants`** (ADMIN_API_KEY + `actor_email`): body `{ tenant_id, name?, slug? }`. Slug validated against `RESERVED_TENANT_SLUGS` and live-uniqueness (409 on conflict); audit + `tenant.updated` outbox event; 404 unknown tenant, no existence leak.
2. **`PATCH /api/admin/machine/workspaces`** (same auth): body `{ workspace_id, name?, slug?, tenant_id? }` where `tenant_id` RE-PARENTS the workspace to another live tenant. Validations: target tenant live (404), `UNIQUE(tenant_id, slug)` conflict on arrival (409), no-op moves allowed. Workspace memberships ride along untouched (they key on workspace_id). Audit + outbox event per the FGA finding above. This is deliberately powerful and operator-only: document that in the route comment.
3. **Console parity (minimal)**: a rename form on the org page tenant section and a rename on workspaces (move stays machine-only); `requirePlatformAdminFromCookies` on page AND actions with non-admin 403 tests.
4. **Analytics door flip**: suite-apps analytics entry becomes `{ kind: 'app-grant' }` (slug `analytics`); launcher tests updated (ungranted users see the request-access card exactly like Studio's).
5. **Plan doc updates in the same commit**: `docs/plans/2026-07-24-authz-hardening.md`: add a dated decision note that the analytics door is now app-grant (supersedes "open" in the entitlements plan), and add gate item 11: "storage-brain onto platform identity + tenant isolation (recon 2026-07-27, plan pending)" with status "not scheduled".
6. **Tests**: rename happy/conflict/reserved-slug paths; move happy/conflict/unknown-target; memberships intact after move; a moved workspace appears under the new tenant in the session verify payload (wire-level assertion); analytics launcher gating; console 403s; machine auth rejects wrong keys.
7. If dependencies change, commit `pnpm-lock.yaml`. `pnpm test && pnpm typecheck && pnpm lint` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push or publish.
- No DELETE semantics changes, no provisioning changes, no MFA/session changes (just merged; do not touch).
- Fail closed; never log tokens/sessions. No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.
