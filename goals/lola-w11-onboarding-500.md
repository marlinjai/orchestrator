---
task: lola-w11-onboarding-500
shared_state: [i18n]
verify: pnpm --filter @lola/api exec jest http-exception relatives && pnpm --filter @lola/api lint && pnpm --filter @lola/web typecheck && pnpm --filter @lola/web i18n:check
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Fix the 500 "internal server error" on the relative onboarding funnel (`/de/onboarding/relative/[id]`) and give the funnel friendly states for invalid/expired links and account-link recovery. Root cause: unmapped Prisma errors fall through to the generic 500.

## Read first

- `apps/api/src/modules/relatives/relatives.service.ts` (around :56-57, `getMyRelative` passes the raw route param into `prisma.person.findUnique`).
- `apps/api/src/common/filters/http-exception.filter.ts` (:20-34, the `AllExceptionsFilter` generic 500 fallback).
- `apps/web/src/app/[locale]/onboarding/relative/[relativeId]/funnel-client.tsx` (:105-107 generic banner; :168 and :576 null-family access).
- `apps/api/src/modules/relatives/relative-onboarding.controller.ts` (reference).

## Definition of done

1. In `AllExceptionsFilter.catch`, map `PrismaClientKnownRequestError` to HTTP statuses BEFORE the 500 fallback: `P2023` (malformed id/inconsistent column data) -> 400, `P2025` (record not found) -> 404. Other Prisma known errors keep a sensible 4xx/500 mapping. This is the load-bearing fix.
2. Defensively validate the id in `getMyRelative`: throw `NotFoundException` for empty/malformed ids instead of letting Prisma throw.
3. In `funnel-client.tsx`, branch on `ApiError.status`: 404 -> "invalid or expired link" state, 403 -> account-link recovery path, instead of the generic amber banner. Add null-family guards at the two access sites.
4. Add unit specs: `http-exception.filter.spec.ts` (maps P2023->400, P2025->404, passes HttpExceptions through, generic Error->500) and a `relatives.service.spec.ts` case covering malformed/missing/not-owned ids.

## Acceptance criteria (incl. unhappy paths)

- Malformed id -> 4xx + friendly "invalid/expired link" state, never a raw 500.
- Well-formed nonexistent id -> 404 + same friendly state.
- Authenticated-but-unlinked relative (person.userId != caller) -> 403 with an account-link recovery path, no dead end.
- Unauthenticated -> login redirect, returns to funnel after, no redirect loop.
- Valid owned id -> funnel loads and resumes (happy path unchanged).
- Null `family` does not crash the client.
- `pnpm --filter @lola/api exec jest http-exception relatives` passes; `pnpm --filter @lola/api lint`, `pnpm --filter @lola/web typecheck`, and `pnpm --filter @lola/web i18n:check` pass.

## Constraints

- Stay in this worktree. Do not push to any remote.
- Do NOT touch `apps/api/src/modules/stories/stories.service.ts` or the story pipeline (reserved for other tasks).
- Any new web user-facing strings go through i18n (de+en parity, ascii-escape + prettier per `i18n:check`). Prefer reusing existing keys; add at most the minimal new keys needed for the 404/403 states. NO em-dash or en-dash.
- Single conventional commit describing the why. Output a final completion message.
