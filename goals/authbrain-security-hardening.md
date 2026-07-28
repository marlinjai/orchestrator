---
task: authbrain-security-hardening
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Pre-launch gate items 1-3 from `docs/plans/2026-07-24-authz-hardening.md`: multi-factor authentication, session hardening with re-auth for sensitive actions, and auth endpoint rate limiting + lockout. This is production auth infra under tier-3 stakes: fail closed everywhere, never log secrets/codes/sessions, mirror the discipline of the existing flows.

## Fixed security parameters (build to these, do not re-decide)

| Parameter | Value |
|---|---|
| MFA method | TOTP (RFC 6238), 30s step, 6 digits, 1-step skew tolerance |
| MFA required for | platform admins (OpenFGA `admin` on `platform:lumitra`) and users holding `owner` on any tenant; optional enrollment for everyone else |
| Recovery codes | 10 per enrollment, single-use, stored hashed (same hashing discipline as passwords) |
| Session absolute lifetime | 14 days (down from current `SESSION_TTL_SECONDS`) |
| Session idle timeout | 72 hours since `last_seen_at` |
| Sudo (re-auth) window | 10 minutes; satisfied by password re-entry OR a TOTP code |
| Sudo-guarded actions | company API key mint/revoke, ownership transfer, erasure request (self-serve AND admin), MFA enroll/disable, password change |
| Login lockout | 10 failed attempts per account per 15 min -> 15 min lock, audited, reset on success |
| Rate limits (Postgres-backed sliding window; no new infra) | login 10/min/IP; signup 5/hour/IP; password reset 3/hour/identifier; oauth callback 20/min/IP |

## Read first

- `docs/plans/2026-07-24-authz-hardening.md` (gate items 1-3)
- `src/lib/session.ts`, `src/lib/crypto/` (password hashing, pgcrypto column encryption: the TOTP secret is stored encrypted the same way), `SESSION_TTL_SECONDS` in shared constants
- `src/lib/flows/` patterns + `src/app/(auth-ui)/` login/signup pages, `api/auth/*` routes
- `src/lib/admin-auth.ts` (how platform-admin is determined), tenant_memberships (owner detection)
- The sensitive routes to guard: `api/orgs/[tenantId]/api-keys*`, `api/orgs/[tenantId]/transfer-ownership`, `api/account/erasure`, admin erasure/user actions
- `src/app/api/oauth/google/callback/route.ts` (see ride-along below)

## Definition of done

1. **TOTP MFA**: enrollment flow in `settings/account` (secret generated server-side, stored pgcrypto-encrypted, otpauth URL + QR rendered, enrollment confirmed by a valid code before activation), recovery codes issued once (hashed at rest, shown once), disable requires sudo. Login: users with MFA enrolled complete a TOTP step (or recovery code, consumed) before the session is issued; users REQUIRED to have MFA (per the table) who are not enrolled are routed into forced enrollment at login before receiving a normal session. Session rows track `mfa_verified_at`.
2. **Session hardening**: absolute 14-day expiry + 72h idle timeout enforced in `verifySessionToken` (idle checked against `last_seen_at` before refreshing it); existing sessions older than the new limits expire naturally (no migration drama). A `reauth_at` timestamp on sessions; `POST /api/auth/reauth` (password or TOTP) sets it; a `requireSudo` guard used by every sudo-guarded action listed above returns a distinct 403 code the UIs turn into a re-auth prompt (no dead ends).
3. **Rate limiting + lockout**: a Postgres-backed sliding-window limiter (single table, pruned opportunistically) applied to the four endpoint groups at the limits in the table; account lockout rows with expiry + audit events on lock/unlock; 429 responses with Retry-After; constant behavior for existing-vs-nonexistent accounts (no enumeration signal).
4. **Ride-along (recorded earlier as tech debt)**: the Google OAuth callback's raw 500 JSON becomes a redirect to `/login?error=oauth` with a friendly message; genuine server errors still logged.
5. **Tests** (unit + DB specs via the Docker-probe pattern; revision paths mandatory): enroll -> disable -> re-enroll; recovery code single-use (reuse rejected); forced enrollment for a tenant owner without MFA; login with wrong/expired TOTP; idle vs absolute expiry each enforced independently; sudo expiry (guarded action passes within window, 403s after); lockout engages at threshold, expires on schedule, resets on successful login; rate limits return 429 then recover; oauth callback redirect; every existing suite stays green.
6. If any npm dependency is added (TOTP/QR lib): run `pnpm install` and COMMIT `pnpm-lock.yaml` in the same commit (the last two waves both missed this).
7. `pnpm test && pnpm typecheck && pnpm lint` green at root. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do not publish packages.
- No SDK/shared published-surface changes (MFA is auth-brain-internal; apps see nothing new). No OpenFGA changes. No Redis or new infrastructure.
- Do not change signup semantics, the app-grant door, erasure logic, or ownership transfer beyond wrapping them in `requireSudo`.
- Never log or expose TOTP secrets, recovery codes, or session tokens on any path, including errors.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
