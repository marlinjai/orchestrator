---
task: lumitra-studio-auth-brain-integration
spec: docs/specs/2026-06-12-auth-brain-session-integration.md
depends_on: [lumitra-studio-brand-db-migration]
shared_state: [lockfile, env]
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

Implement the **Auth Brain session integration** per the spec at `docs/specs/2026-06-12-auth-brain-session-integration.md`: replace the studio's in-app NextAuth layer with session verification against the deployed auth-brain service via `@marlinjai/auth-brain-sdk`, keep the `SERVICE_TOKEN` dual gate byte-identical, stamp the verified session's `active_workspace.id` into `WorkflowRun.workspaceId` at run creation, and REMOVE next-auth entirely. The acceptance bar is the spec's Acceptance section (login round-trip, allowlist second gate, unchanged service path, workspace stamping, next-auth gone, full suite green).

## Read first

- The spec in full: `docs/specs/2026-06-12-auth-brain-session-integration.md`. It contains the verified auth-brain contract (verify route, SDK surface, return_to round-trip, logout route) and the exact env table. Treat it as decided; do not relitigate the allowlist-kept or no-OpenFGA-in-v1 calls.
- The current auth surface you are swapping: `src/middleware.ts`, `src/auth.ts`, `src/lib/auth/{config.ts, verifyRequest.ts, allowlist.ts}`, `src/app/api/auth/[...nextauth]/`.
- The prior art to mirror (read-only, different repo, do NOT modify): `~/software-dev/ERP-suite/projects/analytics-platform/packages/dashboard/src/middleware.ts`, `src/lib/auth.ts`, `src/lib/auth-brain.ts`. Note its `?next=` param is wrong; use `return_to`.
- The SDK source for exact types (read-only): `~/software-dev/ERP-suite/projects/lumitra-infra/auth-brain/packages/sdk/src/{index.ts, client.ts, types.ts}`. Add the dependency as published `@marlinjai/auth-brain-sdk@^1.0.0`, NOT a file: link.
- The run-creation path for workspace stamping: `src/app/api/v1/workflows/run/route.ts`, `src/lib/workflow/repository.ts` (`createWorkflowRun`), `src/lib/workflow/constants.ts` (`DEFAULT_WORKSPACE_ID` stays as the service-token fallback).
- Existing test patterns: `src/middleware.spec.ts` + `vitest.middleware.config.ts` (node env) and `src/lib/auth/__tests__/` (these specs run under the middleware config; keep that split intact, it exists because happy-dom + isolate:false breaks the next-auth mocks; after the swap the same split applies to the SDK mocks).

## Definition of done

1. `@marlinjai/auth-brain-sdk@^1.0.0` added; singleton in `src/lib/auth/auth-brain.ts` per the spec (baseUrl from `AUTH_BRAIN_URL` default `https://auth.lumitra.co`, cookieName `lumitra_session`, 30s cache). Env read LAZILY at call time (mirror the existing middleware pattern; `next build` must not crash without env).
2. `verifyRequest.ts` user branch swapped to `authBrainClient.verifySession(cookie)`; result extends to `{ kind: 'user'; email; userId; workspaceId: string | null }`; allowlist check applied to the verified email (non-allowlisted -> `{ kind: 'none', reason: 'not-allowlisted' }`); service + none branches unchanged; no token/cookie value ever logged.
3. `src/middleware.ts`: page navigation without a valid session redirects to `${AUTH_BRAIN_URL}/login?return_to=<full original URL>`; `/api/*` dual gate (auth-brain session OR `SERVICE_TOKEN`); `/api/health` public; every existing service-token guarantee preserved (constant-time compare, misconfigured-500, nodejs runtime).
4. Workspace stamping: run creation uses the session `workspaceId` when present, else `DEFAULT_WORKSPACE_ID`.
5. Sign-out control posts to `${AUTH_BRAIN_URL}/api/auth/logout` and the user lands back in the login redirect flow.
6. REMOVED in this same slice: `next-auth` from package.json, `src/auth.ts`, `src/lib/auth/config.ts`, `src/app/api/auth/[...nextauth]/`, the in-app `/login` page. No deprecated shims left behind.
7. Dev bypass: `AUTH_DEV_USER_EMAIL` honored ONLY when `NODE_ENV === 'development'`; a test asserts it is ignored in production.
8. Tests per the spec's list, SDK client mocked, no network. Full `pnpm test` (the infisical-wrapped suite, both vitest configs) GREEN, plus lint + typecheck.
9. `docs/internal/auth.md` rewritten. Spec frontmatter stays `decided`.
10. Single conventional commit describing the WHY (absorb the stopgap in-app auth into the live shared identity service; real workspace ids reach the run envelope).

## Constraints (hard, do not violate)

- Do NOT call auth.lumitra.co (or any network) from tests. Mock the SDK.
- Do NOT weaken or alter the `SERVICE_TOKEN` path. Do NOT log secrets or cookie values.
- Do NOT add OpenFGA / `can()` wiring, workspace switching UI, or per-workspace scoping of Asset/Project/Job. Out of scope (note as `open_thread` if tempted).
- Do NOT touch `prisma/schema.prisma` or migrations (the workspaceId column already exists). If you believe a schema change is needed, that is a `scope_change`: escalate.
- Do NOT modify the analytics-platform or auth-brain repos. Read-only references.
- Stay in this worktree. Do NOT push to any remote. No em-dashes or en-dashes anywhere. Report via `update_state` (`file_touched`, `decision`, `open_thread`, `commit`).

## Notes

- The brand-db slice may have merged just before this one; if `verifyRequest` or routes moved slightly, the actual code is the source of truth, the spec's intent governs.
- Infisical/Coolify env cleanup (removing the old AUTH_GOOGLE_* secrets, adding AUTH_BRAIN_URL) is the operator's post-merge step; just list what changed in your final message.
- If the published SDK version on npm differs from 1.0.0, use the latest 1.x and note it as a `decision`.
