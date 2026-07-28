---
task: auth-brain-workspace-key-grants
spec: docs/plans/2026-07-24-authz-hardening.md (decision 2, app-grant door) + storage-brain docs/plans/2026-07-27-company-isolation.md (S1)
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: workspace-scoped API keys must carry their parent company's app_grants

## The bug (found live in production 2026-07-27)

`appGrantsForScope` in `packages/app/src/lib/flows/api-keys.ts` returns `[]` for
every non-`tenant` scope:

```ts
async function appGrantsForScope(sql, scope): Promise<string[]> {
  if (scope.type !== 'tenant') return [];
  return listAppGrantsForTenant(sql, scope.id);
}
```

Its comment justifies this as avoiding "an aggregate that would blur the billing
unit". That reasoning is correct for `tenant_group` (spans many companies) but
WRONG for `workspace`: a workspace belongs to exactly ONE company, so delivering
that company's grants is not an aggregate and does not blur the billing unit.

The consequence is a shipped, structurally-dead code path plus a latent
production outage:

- storage-brain S1 (`packages/api/src/middleware/auth.ts`) accepts BOTH
  `workspace`- and `tenant`-scoped auth-brain keys, and requires the `storage`
  app grant on both branches before resolving the storage tenant.
- Because auth-brain never sends grants on a workspace scope, the workspace
  branch can NEVER pass its own grant door. Every workspace-scoped key gets
  `403 "This company is not granted the storage app"`, no matter what grants
  the company actually holds.
- Verified live: lola-stories production holds a workspace-scoped auth-brain key
  (scope `019f6a89-ea52-7097-8674-e2c729bd3ca9`, the workspace the lola-stories
  storage tenant is bound to via `auth_workspace_id`). The `storage` grant for
  the lola-stories company was seeded on 2026-07-27 and the key STILL 403s.
- storage-brain's own unit tests pass only because they mock a verify response
  carrying `app_grants: ['storage']` on a workspace scope, which real auth-brain
  never produces. This is exactly the mocked-boundary/schema-parity failure mode
  in `knowledge-base/standards/stateful-flow-testing.md`.

## What to change

In `packages/app/src/lib/flows/api-keys.ts`:

1. `appGrantsForScope` resolves grants as follows:
   - `tenant` scope: the company's own live grants (UNCHANGED).
   - `workspace` scope: look up the workspace's parent company
     (`findWorkspaceById` in `packages/app/src/lib/db/repositories/workspaces.ts`
     exposes the workspace row; use its tenant id) and return THAT company's live
     grants via `listAppGrantsForTenant`.
   - `tenant_group` scope: `[]` (UNCHANGED, and keep a comment saying why: a
     group spans multiple companies, so there is no single billing unit).
   - A workspace id that resolves to no workspace (deleted/unknown) returns `[]`,
     never throws: verify must stay fail-closed, and `[]` denies at the app door.
2. Replace the now-inaccurate comment with one that states the real rule:
   entitlements are a COMPANY concept; a workspace inherits its company's grants
   because its company is unambiguous; a tenant_group does not because it spans
   companies.

Keep the change minimal and surgical. Do NOT refactor the verify path, do NOT
change the wire shape (`scope.app_grants` already exists on every scope), and do
NOT touch the session verify route.

## Tests (required)

- Unit/integration coverage in the api-key verify path proving:
  - a workspace-scoped key whose company HAS a grant receives that grant slug;
  - a workspace-scoped key whose company LACKS the grant receives `[]`;
  - a workspace-scoped key for a soft-deleted/unknown workspace receives `[]`
    (fail-closed, no throw);
  - a tenant-scoped key is unchanged;
  - a tenant_group-scoped key still receives `[]`.
- Update any existing fixture that encodes the old behavior (there is at least
  one workspace-scoped fixture with `app_grants: []` in
  `packages/app/src/app/api/verify/api-key/route.spec.ts`) so it reflects the new
  rule INTENTIONALLY rather than incidentally. Do not delete tests to make the
  suite green; adapt them and keep the assertion count at least as high.
- Keep/extend `packages/app/src/app/api/verify-wire-contract.spec.ts` so the real
  response still parses with the PUBLISHED shared zod schema.

## Definition of done

- The five test cases above pass.
- The verify chain in this goal's frontmatter (which mirrors CI's order: build
  shared, build sdk, typecheck, lint, test, build) exits 0.
- `pnpm --filter @auth-brain/app test:integration` needs live Postgres + OpenFGA
  (`docker compose up -d postgres openfga`). Run it if docker is available in
  your environment; if it is not, say so explicitly in your final message so the
  operator runs it before merge. Do NOT weaken or skip integration tests to make
  a gate green.
- No wire-shape change, so no shared/SDK version bump is required. If you believe
  a bump IS required, stop and say why rather than bumping.
- Commit message: `fix(api-keys): workspace-scoped keys inherit their company's app_grants`

## Constraints

- Do NOT touch: MFA/session-hardening code, the erasure wave, the outbox, the
  FGA model, or any registry entry.
- Do NOT change `listAppGrantsForTenant` semantics.
- This repo is the live identity service for the whole suite. Prefer the smallest
  correct diff. If a change seems to require touching auth or session semantics,
  stop and escalate instead.
