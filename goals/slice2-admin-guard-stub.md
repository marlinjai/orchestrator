---
task: slice2-admin-guard-stub
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-admin-guard-stub.md
depends_on: ["track0-backend-foundation"]
shared_state: []
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone interim admin guard stub (slice2-admin-guard-stub)

This is part of the framer-clone build (build-2026-06, cms-content-tier track, wave 1). Build EXACTLY the slice2-admin-guard-stub spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-admin-guard-stub.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/server/auth/guard.ts`: a tiny `can(principal, action, resource)`-shaped authorization seam guarding CMS (and later commerce) WRITE routes. First line `import 'server-only'`.
- `Principal { userId, workspaceId, isAdmin }` interface plus a `can(principal, action, resource): boolean` function whose signature is auth-brain-shaped (matches a future `auth.can` so the later swap is an adapter change, not a rewrite).
- `getPrincipal(req): Principal | null` reads the interim shared secret from a header or cookie and compares it against an env-injected value. The interim secret comes from `process.env` (Infisical-injected), NEVER a literal in source.
- `requireAdmin(req): { ok: true; principal } | { ok: false; response }` returning a Track-0 envelope: correct secret yields `{ok:true,principal}` with `isAdmin:true` and the constant workspace, missing secret yields a 401 envelope, wrong secret yields a 403 envelope.
- One hard-coded admin principal plus one `INTERIM_WORKSPACE_ID` constant for v1 (single workspace/tenant).
- `src/server/auth/__tests__/guard.test.ts` (node vitest project): cover correct, missing, and wrong secret cases; assert errors surface (401 / 403) and are never swallowed; assert the `can()` signature is auth-brain-shaped.
- Reuse the Track-0 envelope helpers and the server-only boundary established by `track0-backend-foundation` (a dependency of this slice).

## Hard constraints (do NOT)

- Do NOT integrate the real auth-brain (P2 / E7, explicitly deferred). The `can()` signature only needs to MATCH the future `auth.can` shape.
- Do NOT build end-user auth or `app_users` (P6). Do NOT add multi-workspace resolution (E7; one constant workspace for v1).
- Do NOT add the guard to read routes. Reads (storefront, binding preview) stay UNAUTHENTICATED for v1; only mutation routes call `requireAdmin(req)`. Read routes must NOT import the guard (a documented contract here, grep-verifiable once those routes exist).
- Do NOT build other slices' or tracks' surface: no CMS adapter/repo, no commerce models or routes, no checkout route, no Prisma changes. This slice ships ONLY `src/server/auth/guard.ts` plus its test.
- This slice declares NO shared state (`sharedState: []`, `touchesSharedState: false`). Do NOT touch any shared state owned by another spec: do NOT edit `prisma/schema.prisma`, the lockfile, `next.config`, or `vitest.config` beyond what already exists from Track 0. Do NOT touch MST. Keep changes minimal and confined to `src/server/auth/`.
- The interim secret is read from env only; NEVER write a literal secret in source, NEVER a `.env` file. Secrets via Infisical only (split-responsibility: the Worker writes the env READ, Marlin sets the value in Infisical). Confirm the framer-clone Infisical secret NAME is left as an open question for Marlin, do not invent and hard-code a value.
- Errors must surface, never be swallowed: missing/wrong secret returns 401/403, it does not silently pass.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
