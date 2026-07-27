---
task: analytics-grant-door
depends_on: [authbrain-admin-api-completeness]
verify: pnpm exec vitest run && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Analytics' door becomes grant-gated: a signed-in suite user may enter (and create projects) only if one of their companies carries the `analytics` app grant in the verify payload. Inner per-project authorization stays exactly as it is (its consolidation onto the decision plane is gate item 9, a separate slice). Operator decision 2026-07-27, superseding the open-door choice.

## Read first

- `packages/dashboard/src/middleware.ts`, `src/lib/auth.ts`, `src/lib/auth-api.ts` (`authenticateAccountRequest`), `src/app/api/projects/route.ts` (project creation currently open to any session)
- The Studio gate as reference: lumitra-studio `src/lib/auth/verifyRequest.ts` + `appGrants.ts` (grant extraction from `session.tenants[].app_grants`, the version-skew log line pattern)
- `@marlinjai/auth-brain-shared@^1.4.0` types (tenants[].app_grants)
- The repo verify chain: `pnpm exec vitest run && pnpm typecheck && pnpm lint && pnpm build` (CI builds; match it)

## Definition of done

1. **Door**: every authenticated page/API path (except the signed erasure webhook and public tracker/config endpoints, which keep their existing auth models) requires `'analytics'` in the union of the session tenants' `app_grants`. Missing field entirely (version skew) fails closed with the distinct grep-able log line pattern. Ungranted signed-in users land on a request-access page (no dead end), not an empty app.
2. **Project creation** (`POST /api/projects` and the owner self-heal path) requires the grant like everything else.
3. Shared/SDK pins bumped as needed for the `app_grants` types (`shared ^1.4.0`); lockfile committed.
4. **Tests**: granted user passes; ungranted user blocked on pages, APIs, and project creation; skew case logs + fails closed; public tracker/config endpoints unaffected; erasure webhook unaffected; existing suites green.
5. `pnpm exec vitest run && pnpm typecheck && pnpm lint && pnpm build` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push.
- Do NOT touch per-project authorization internals, ClickHouse queries, ingestion, or the erasure consumer.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.

## Notes

- The `analytics` grants will be seeded by the operator BEFORE this deploys (so nobody gets locked out); the registry-side flip ships in the auth-brain slice this depends on.
