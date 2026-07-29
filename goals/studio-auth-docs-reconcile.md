---
task: studio-auth-docs-reconcile
shared_state: []
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Reconcile `docs/internal/auth.md` with what actually shipped for Studio auth. The doc predates "Track B" (PR #45) and is now stale: it still describes the gate as OpenFGA-free and lists `STUDIO_PERMISSIONS` / `can()` as out of scope, while the running code wires OpenFGA and enforces resource-level `can()` at every mutating route. Bring the doc to ground truth as of 2026-06-25. This is a DOCS-ONLY change: do not touch any TypeScript.

## Read first (ground truth, do not change these files)

- `docs/internal/auth.md` (the stale doc you are fixing)
- `src/lib/auth/verifyRequest.ts` (the single auth seam: precedence policy, dual-token compare, membership gate, dev bypass)
- `src/lib/auth/can.ts` (`STUDIO_PERMISSIONS` mapping `studio.generate` / `studio.workflow.run` / `studio.brand.write` / `studio.session.write` to `workspace.member`; `authorizeMutation`; `guardMutation`; fail-closed on throw)
- `src/lib/auth/auth-brain.ts` (the SDK client singleton + the `OPENFGA_API_URL` / `OPENFGA_STORE_ID` / `OPENFGA_AUTHORIZATION_MODEL_ID` / `OPENFGA_API_TOKEN` wiring)
- `src/lib/auth/workspace.ts` (the slug-based membership gate, `STUDIO_WORKSPACE_SLUG` default `lumitra-studio`)
- `src/middleware.ts` (page vs `/api/*` split, `/api/health` + `/no-access` public)
- `docs/specs/2026-06-12-auth-brain-session-integration.md` and `docs/specs/2026-06-13-studio-workspace-membership-gate.md` (the two accurate specs; the "Reality update" note in the 06-12 spec is authoritative)
- `package.json` (the installed `@marlinjai/auth-brain-sdk` version)

## Definition of done

Rewrite `docs/internal/auth.md` so it accurately states:

1. **Two caller classes through one seam (`verifyRequest`):** browser sessions verified against live `auth.lumitra.co` via `@marlinjai/auth-brain-sdk` (cookie `lumitra_session`, 30s cache); machine callers via `SERVICE_TOKEN` bearer. An `Authorization` header is treated as machine intent and never falls through to the cookie path.
2. **The coarse gate is workspace membership** (member of the `lumitra-studio` workspace, matched by slug from the session's `workspaces[]`), which REPLACED the old `AUTH_ALLOWED_EMAILS` allowlist. Granting access = inviting an email to the workspace in auth-brain, no code change. Re-checked every request (30s cache), so revocation takes effect on the next call.
3. **The inner boundary is resource-level `can()` (Track B, PR #45):** `guardMutation('studio.<action>')` at every mutating route, `STUDIO_PERMISSIONS` maps the four action names to the OpenFGA `workspace.member` requirement, fail-closed (a throw OR a `false` is a 403). Document the `OPENFGA_*` env vars the client now reads, and that service-token + dev-bypass callers pass BEFORE `can()`.
4. **`SERVICE_TOKEN` / `SERVICE_TOKEN_NEXT` dual-accept rotation** (constant-time, all tokens run to completion so the valid set is not latency-distinguishable). Cross-link `docs/internal/service-token-rotation.md`.
5. **Dev bypass:** `AUTH_DEV_USER_EMAIL` honored only when `NODE_ENV === 'development'`, returns a user with `workspaceId: null` (skips membership AND `can()`), ignored in production.
6. **Version reconcile:** cite the `@marlinjai/auth-brain-sdk` version actually pinned in `package.json` (the older specs say 1.0.0/1.0.1; the doc must match the installed `^1.x`).
7. Add a dated "Current as of 2026-06-25" note at the top and cross-link the two accurate specs (2026-06-12, 2026-06-13).

Remove any line that says OpenFGA is out of scope / not wired in v1, or that `can()`/`STUDIO_PERMISSIONS` are future work. Keep the still-true `Project.workspaceId` vs `WorkflowRun.workspaceId` naming-collision note (it is genuinely deferred).

Plus, always:
- the `verify` gate command passes (it will, since no code changes)
- single conventional commit on this branch describing the WHY (docs reconciled to the shipped Track B reality)

## Constraints

- DOCS ONLY. Do not modify any `.ts`/`.tsx`. No behavior change.
- No em-dashes or en-dashes anywhere in the doc (use colon, parentheses, comma, period).
- Stay in this worktree. Do not push to any remote. Do not merge.
- If you find an auth-related inaccuracy in ANOTHER doc while reading, do not fix it here; record it as an `open_thread` via update_state.
- When done, output a final message that the task is complete.
