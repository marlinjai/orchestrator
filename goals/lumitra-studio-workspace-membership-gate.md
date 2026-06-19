---
task: lumitra-studio-workspace-membership-gate
spec: docs/specs/2026-06-13-studio-workspace-membership-gate.md
shared_state: [env]
verify: pnpm test
verify_fix_cap: 3
verify_timeout_s: 1800
marlin_proxy: live
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement the **workspace-membership access gate** per the spec at `docs/specs/2026-06-13-studio-workspace-membership-gate.md`: replace the `AUTH_ALLOWED_EMAILS` allowlist with "the verified auth-brain session is a member of the Lumitra Studio workspace," read straight from the session's `workspaces[]` (no OpenFGA, no `can()`, no new infra). Stamp the matched workspace id onto human-session workflow runs. The spec's Decisions section is settled; do not relitigate.

## Read first

- The spec in full: `docs/specs/2026-06-13-studio-workspace-membership-gate.md`.
- `src/lib/auth/verifyRequest.ts` (the seam you change), `src/lib/auth/allowlist.ts` (the file you DELETE), `src/lib/auth/auth-brain.ts` (the SDK singleton + `SESSION_COOKIE_NAME`).
- `src/middleware.ts` + `src/app/no-access/page.tsx` (rename the reason `not-allowlisted` -> `no-workspace-access`; keep the redirect/401 split unchanged).
- Run-creation path: `src/app/api/v1/workflows/run/route.ts`, `src/lib/workflow/repository.ts` (`createWorkflowRun`), `src/lib/workflow/constants.ts` (`DEFAULT_WORKSPACE_ID` stays the service-token fallback).
- The SDK payload: `@marlinjai/auth-brain-sdk` `verifySession()` returns `SessionVerifyResponse` with `workspaces: Array<{ id; slug; name; role; ... }>` (confirmed: `Workspace` has a `slug`). Match membership on `slug === STUDIO_WORKSPACE_SLUG` (default `lumitra-studio`).
- Existing test patterns: `src/middleware.spec.ts` + `vitest.middleware.config.ts` (node env), `src/lib/auth/__tests__/`. The SDK is mocked at the `getAuthBrainClient` seam (see how middleware.spec mocks `verifySession`).

## Definition of done

1. `verifyRequest.ts` user branch: verify session -> if `workspaces.some(w => w.slug === STUDIO_WORKSPACE_SLUG)`, return `{ kind: 'user', email, userId, workspaceId: <matched workspace id> }`; if verified but not a member, `{ kind: 'none', reason: 'no-workspace-access' }`. `STUDIO_WORKSPACE_SLUG` read lazily, default `lumitra-studio`. Never log the cookie/session.
2. DELETE `src/lib/auth/allowlist.ts` + all `AUTH_ALLOWED_EMAILS` references (code, env example, docs, tests). The allowlist concept is gone.
3. Run creation stamps the session `workspaceId` for human callers; service-token runs keep `DEFAULT_WORKSPACE_ID`.
4. Middleware + `/no-access`: rename reason to `no-workspace-access`; redirect/401 split unchanged; `/no-access` stays public.
5. Dev bypass `AUTH_DEV_USER_EMAIL` (development only) still yields a user result and bypasses the membership check; a test asserts it is ignored in production.
6. Tests (both configs, SDK mocked, no network): member of `lumitra-studio` -> user + that workspace id; verified non-member -> none/`no-workspace-access` -> `/no-access` (307); session-less -> hosted login (307 to `/login`); SERVICE_TOKEN unchanged; dev bypass dev-only. Full `pnpm test` GREEN, typecheck + lint clean.
7. `docs/internal/auth.md` updated (gate = workspace membership; access granted via the auth-brain admin console invite-to-workspace).
8. File an `open_thread` for the `Project.workspaceId` (Storage Brain) vs auth-brain-workspace naming collision noted in the spec; do NOT rename it here (would pull in a migration).
9. Single conventional commit describing the WHY (the email allowlist was a stopgap; Studio access is auth-brain workspace membership, the decided suite pattern).

## Constraints (hard, do not violate)

- Do NOT add OpenFGA / `can()` wiring or `OPENFGA_*` env. The session's `workspaces[]` is the entire gate (spec's key simplification). Adding OpenFGA is a `scope_change`: escalate.
- Do NOT touch `prisma/schema.prisma` or migrations (the `WorkflowRun.workspaceId` column already exists). Do NOT rename `Project.workspaceId` here (open_thread only).
- Do NOT change OAuth/session/logout logic, the SDK, or the SERVICE_TOKEN path semantics.
- Do NOT build a Studio-native invite UI (auth-brain owns membership management).
- Stay in this worktree; do NOT push. No em/en-dashes. Report via `update_state`.

## Notes

- Prereq for a human to actually get in after this merges (operator step, NOT yours): a `lumitra-studio` workspace must exist in auth-brain and the user must be a member. That is data provisioning via the auth-brain admin console, tracked separately; this slice is the code that consumes it. The gate failing closed (no workspace -> `/no-access`) is correct behavior until provisioning happens.
- If the studio test DB / Infisical is unreachable in the worktree, file an `open_thread` and stop rather than stubbing; the prior slices ran `pnpm test` fine against the local studio Postgres on 5432.
