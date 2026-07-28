---
task: storage-hygiene
verify: pnpm run build && pnpm run typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice S3 of `docs/plans/2026-07-27-company-isolation.md` (READ IT, including the 2026-07-27 S2 amendment): close the recon's hygiene findings without touching the auth model S1 just shipped.

## Definition of done

1. **Signed upload webhook**: `POST /webhooks/r2-upload-complete` requires an HMAC-SHA256 signature over the raw body using a new env `R2_WEBHOOK_SIGNING_SECRET` (constant-time compare, min length, 401 fail-closed, 500 when env unset). Whatever CALLS this webhook (R2 event notification config or an internal caller; find it) is documented in the route comment; if the caller cannot sign (external R2 config), gate instead by a shared token query/header per that caller's capability and say so explicitly. Tests: valid/invalid/missing/env-missing.
2. **Per-tenant URL key derivation**: signed/permanent/upload tokens derive their key via HKDF(URL_SIGNING_SECRET, tenantId) instead of using the global secret directly, WITH BACKWARD COMPATIBILITY: verification accepts BOTH the derived and the legacy global-secret signature during a deprecation window (constant flag in code, documented), so no live URL breaks now; new tokens are minted derived-only. Tests cover both accept paths + cross-tenant token rejection.
3. **`X-Workspace-Id` resolved**: the header the SDK sends but nothing reads: implement server-side enforcement (when present, the request's workspace param/results must match it, 400 on mismatch) OR delete it from the SDK; pick based on which is less breaking for existing consumers, justify in a comment, and version the SDK if its surface changes.
4. **Rate-limit note**: leave the in-memory store, but add the horizontal-scale caveat comment where it is defined (recon finding 11; no infra change).
5. `pnpm run build && pnpm run typecheck && pnpm lint && pnpm test` green. Single conventional commit; lockfile committed if deps change.

## Constraints

- Stay in this worktree. Do not push/publish. Do not touch S1's auth middleware classes, tenant splitting, CORS (the dashboard upload depends on it; leave with a comment), or the erasure consumer (S4).
- Never log secrets/tokens. No em-dashes or en-dashes. Final message when complete.
