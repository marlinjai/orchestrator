---
task: authbrain-era3-convergence
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Auth-brain side of the era-3 convergence wave (pre-launch gate items 6 + 7, plan `docs/plans/2026-07-24-authz-hardening.md` + erasure follow-ups in `docs/plans/2026-07-24-gdpr-erasure.md`): (1) an app-grant access mode in the published `@marlinjai/auth-brain-nextjs` wrapper so the Receipts app can migrate off the `receipts-` workspace-slug-prefix door, (2) the suite-apps registry flip for receipts, (3) the erasure fan-out payload extension + analytics registry entry that the analytics erasure consumer needs. Two follow-up slices in OTHER repos depend on the packages this slice bumps; do NOT publish npm packages (operator publishes after merge).

NOTE: "lazy Main workspace" is explicitly DEFERRED out of this wave: receipts scopes data per workspace, so companies must keep receiving a default workspace until receipts is rearchitected. Do not touch provisioning.

## Read first

- `packages/nextjs/src/workspace.ts` (`matchWorkspaces`), `packages/nextjs/src/verifyRequest.ts`, `packages/nextjs/src/__tests__/` (the wrapper you extend; its config shape and AuthResult contract MUST stay backward compatible)
- `packages/shared/src/types.ts:121-127` (tenants[] with `app_grants`), and the session verify response including `workspaces[].tenant_id`
- `packages/app/src/lib/suite-apps.ts` (registry: `app-grant` kind exists; receipts currently `workspace-slug-prefix`), `docs/internal/consuming-apps.md`
- `packages/app/src/lib/erasure/fanout.ts` + `webhook-signature.ts` + the E2 erasure flows and specs (payload you extend)
- `packages/shared/src/schemas.ts` (erasure webhook payload schemas)

## Definition of done

1. **`@marlinjai/auth-brain-nextjs` app-grant mode**: the config's access declaration becomes a union: the existing `workspaces: { slugPrefix }` mode (unchanged behavior, all existing tests stay green) OR a new `appGrant: { app: string }` mode. In appGrant mode the membership set = the session's `workspaces[]` whose `tenant_id` belongs to a tenant whose `app_grants` contains the app slug (the payload already carries both sides of the join; no extra network call). Same downstream `AuthResult`/`AppSession` shape (memberships `{id,slug,role}[]`, activeWorkspace cookie resolution, `no-workspace-access` reason when the set is empty), same service-token precedence, same dev bypass. Tests for both modes incl. the granted-tenant-with-zero-workspaces edge (empty memberships -> no-access, no crash). Bump `packages/nextjs` to `0.2.0` and its `@marlinjai/auth-brain-shared` peer/dep range to `^1.4.0`.
2. **Registry flip**: suite-apps receipts entry -> `{ kind: 'app-grant' }` (slug `receipts`); launcher tests updated; `docs/internal/consuming-apps.md` row updated. The magic-workspace DELETION is an ops step after the receipts app migrates; no code here.
3. **Erasure payload extension** (additive): `tenant.erased` webhook payload gains `workspace_ids: string[]` (the erased tenant's workspace ids, collected BEFORE deletion in the cascade); shared schemas/types updated; E2 fan-out + signature specs updated; bump `packages/shared` to `1.4.0`. Consumers on 1.3.0 shapes must still parse (additive field only).
4. **Analytics erasure registry entry**: suite-apps `erasure` entry for analytics: url `https://analytics.lumitra.co/api/internal/erasure`, secret name `ANALYTICS_ERASURE_WEBHOOK_SECRET` (name only; operator scaffolds the value). Delivery to a not-yet-deployed consumer must keep degrading to visible retries exactly like the Studio entry did in E2.
5. `pnpm test && pnpm typecheck && pnpm lint` green at root. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do not publish npm packages.
- Backward compatibility is binding: slugPrefix mode, the AuthResult contract, and the 1.3.0 webhook payload shape (minus the new additive field) must not change.
- No provisioning changes (lazy Main deferred). No OpenFGA changes. Fail closed; never log sessions/keys/webhook bodies.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
