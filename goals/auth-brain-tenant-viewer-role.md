---
task: auth-brain-tenant-viewer-role
spec: docs/plans/2026-07-24-authz-hardening.md pre-launch gate item 10 (DECIDED YES 2026-07-27) + docs/internal/authorization-overview.html section 05
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: add the tenant-level `viewer` role (pre-launch gate item 10)

Marlin APPROVED a tenant-level `viewer` role on 2026-07-27, settling gate item 10.
It is a read-only rung on the COMPANY ladder, deliberately chosen instead of
building custom roles (see `docs/internal/custom-roles-tradeoffs.html` section 04:
"adding one well-chosen rung to the PLATFORM ladder... costs a fraction and keeps
every guarantee"). Studio's role matrix gates its read tier on this role, so this
slice unblocks that one.

## Current state

- `TenantRole` is `owner | admin | billing_admin | member`
  (`packages/shared/src/types.ts` around the role unions; arrays in
  `packages/shared/src/constants.ts`).
- Only `workspace` has a `viewer` relation in
  `packages/app/src/lib/openfga/schema.json`, defined as
  `viewer = this OR member` (a SAME-SCOPE hierarchy).
- `@marlinjai/auth-brain-shared` is at 1.5.0 and `-sdk` at 1.4.0, both freshly
  published. Verify the actual current versions yourself before bumping.

## What to build

1. **The role itself:** add `viewer` to the tenant role union, the role
   constants/arrays, and the zod schemas that validate roles. Find every
   exhaustive switch or union-typed mapping over `TenantRole` and handle the new
   member explicitly — a compile error is the point; do not paper over one with a
   default branch that silently grants more than viewer.

2. **The FGA model** (`schema.json`): add `tenant.viewer` as a SAME-SCOPE
   hierarchy mirroring the workspace pattern: `viewer = this OR member`, so any
   member/admin/owner is also a viewer of that company. It must NOT cascade
   across tiers (a company viewer gets nothing on workspaces beneath it, and an
   org-level role does not confer company viewer beyond the existing management
   cascade). Ordering matters: read the current model first, because it already
   carries inheritance rewrites from the B-sync slice.

3. **Ranking:** `viewer` is the LOWEST rung. Anywhere roles are compared or
   ordered (minimum-role checks, "is this role at least X" helpers, UI sorting),
   viewer must rank below `member`. Never let a viewer satisfy a member-or-above
   check.

4. **Assignment surfaces:** the machine memberships API, the admin console role
   pickers, and the settings/companies role selectors must offer `viewer` for
   tenant scope. Do not add it to scopes that should not have it.

5. **Publishes:** bump shared + sdk (additive minor). Do NOT publish; the
   operator does that.

## Guard rails (read carefully)

- `viewer` is READ-ONLY. It must never satisfy a gate for a mutating action
  anywhere in auth-brain: no key minting, no membership changes, no ownership
  transfer, no deletion, no billing.
- Do not change the existing cascade semantics from the B-sync slice
  (`workspace.member` must NOT regain a `tenant#member` arm; `member` and
  `billing_admin` still never cascade across tiers).
- Adopting a new FGA model is MANUAL (push, then set
  `OPENFGA_AUTHORIZATION_MODEL_ID`). State in your final message that the
  operator must do this, or the role exists in code but not in the live graph.

## Tests (required)

- A tenant `viewer` can READ (verify payload reports the role; any read-gated
  auth-brain surface accepts it) and is DENIED on every mutating gate listed
  above. Assert the denials explicitly, one per action class.
- Role ranking: viewer does NOT satisfy a `member`-or-above check; member,
  admin and owner all DO satisfy a viewer-or-above check.
- Same-scope hierarchy holds in the real model: a company member/admin/owner is
  also a company viewer.
- No cross-tier leak: a company viewer gets NO workspace access.
- The B-sync inheritance tests still pass unchanged.
- Use the REAL OpenFGA integration harness for the model assertions
  (`packages/app/tests/integration/inheritance-openfga.spec.ts` is the template);
  the in-memory mock cannot evaluate userset rewrites.

## Definition of done

- Verify chain in the frontmatter exits 0.
- Integration suite run if docker is available; say so explicitly if not (CI gates).
- Final message states the shared/SDK versions you bumped to and the manual model
  push the operator must run.

## Constraints

- Live identity service: smallest correct diff.
- Do NOT touch storage-brain, Studio, or analytics in this slice.
- Do NOT implement per-tenant configurable roles; this is one fixed rung.
