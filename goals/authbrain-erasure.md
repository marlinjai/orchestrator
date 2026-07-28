---
task: authbrain-erasure
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice E2 of the GDPR erasure plan: the erasure state machine, deletion surfaces, company cascade logic, pseudonymization, and the signed erasure-webhook fan-out. The governing plan is `docs/plans/2026-07-24-gdpr-erasure.md` in this repo: read it FIRST and treat its "Legal model", "Erasure state machine", and "App fan-out contract" sections as binding. Slice E1 (ownership transfer) is already merged on this branch's base; use its flow for nothing here, it is only the user-facing unblock path.

## Read first

- `docs/plans/2026-07-24-gdpr-erasure.md` (binding)
- `src/lib/flows/` patterns (signup, companies, ownership-transfer), `src/lib/outbox.ts` + `src/lib/openfga/sync-worker.ts` (worker loop + outbox mechanics you will reuse for webhook delivery), `src/workers/outbox-sync.ts`
- `src/lib/admin-auth.ts` + admin console patterns (per-page AND per-action gates), `settings/account` page, machine API patterns, `suite-apps.ts` (registry you extend with `erasure` entries)
- `packages/shared/src/types.ts` (OutboxEventType)

## Definition of done

1. **State machine + persistence**: `erasure_requests` table (user_id, status: requested | undo_window | executing | blocked_on_transfer | completed | cancelled, requested_at, execute_after = requested_at + 14 days, completed_at, blocked_scopes jsonb, per-app ack state). Survives restart; all transitions audited.
2. **Request surfaces**: self-serve in `settings/account` ("Delete account": re-enter password + typed email confirmation; all sessions killed immediately; a login during the window lands on a cancel-or-nothing page); admin console user page "Delete user" (typed confirmation, gated page AND action, non-admin 403 tests); machine API `POST /api/admin/machine/erasure` (+ GET status, DELETE to cancel within window).
3. **Executor**: rides the existing worker process (same container as outbox-sync): polls due requests. Per company of the user: sole member of a personal-group company -> FULL cascade (workspaces, memberships, app_grants, service accounts + their keys, then `tenant.erased` webhook + soft-delete tenant + group); sole OWNER with other members -> `blocked_on_transfer`, recorded in `blocked_scopes`, surfaced to the requester AT REQUEST TIME and re-checked each poll (ownership transfer or admin dissolution unblocks); plain membership -> membership removal only (normal membership.revoked events so OpenFGA cleans up).
4. **User finalization**: anonymize the user row (email -> deterministic tombstone hash, name null), delete credentials, sessions, api keys they hold, invitations addressed to them; PSEUDONYMIZE audit/outbox history (their email/name replaced by the tombstone token; ids may remain); `user.erased` webhook; status `completed` only when every registered app acked every event.
5. **Webhook fan-out** (plan contract, binding): registry `erasure` entries per app (url + Infisical secret NAME; add the Studio entry pointing at `https://studio.lumitra.co/api/internal/erasure` with secret name `STUDIO_ERASURE_WEBHOOK_SECRET`; do NOT put secret values anywhere). HMAC-SHA256 over the raw body, header signature; delivery via the outbox mechanics (retries, backoff, dead-letter + loud log on exhaustion); idempotent by event_id; per-app ack tracked on the request row. The Studio endpoint DOES NOT EXIST until slice E3 deploys: delivery failure must degrade to retries + visible "awaiting app" state, never block this slice's merge or crash the worker.
6. **Events**: `user.erased`, `tenant.erased` added to `OutboxEventType` as audit-only for OpenFGA (comment at `tuplesFor` default, same pattern as app_grant.*); membership removals during cascade emit the NORMAL membership events so FGA tuples clean up.
7. **Admin visibility**: an Erasures section in the admin console: pending/blocked/executing/completed requests, blocked scopes, per-app ack status, day counter against the one-month clock with a visual warning past day 21. Gated per page and per action.
8. **Tests** (unit + DB specs with the Docker-probe pattern; revision paths are MANDATORY per the plan): cancel during window restores full function; re-request after cancel; blocked -> transfer -> completes; executor resumes correctly after restart mid-execution; sole-member cascade removes everything incl. grants and keys; multi-member company survives minus the user; pseudonymization leaves no email/name in audit rows for the tombstoned user; webhook signing verified against a fixture, replayed event_id no-ops, retry path on 404/timeout; admin 403s; machine API auth.
9. `pnpm test && pnpm typecheck && pnpm lint` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do NOT implement the Studio consumer (slice E3).
- No real secret values anywhere; the webhook secret is referenced by NAME and read from env at runtime (env var `STUDIO_ERASURE_WEBHOOK_SECRET`, documented in the PR body for the operator to scaffold).
- Do not weaken any existing auth discipline; never log tokens, cookies, webhook bodies containing emails, or secrets.
- Billing/invoice retention: implement ONLY the `retention_hold` seam described in the plan (flag + expiry on quarantined rows), no invoice store.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
