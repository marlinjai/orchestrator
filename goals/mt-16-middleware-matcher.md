---
task: mt-16
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-09, mt-10]
shared_state: [next-config]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-16** (section "MT-16 - Reconcile the middleware matcher + gate /projects + encode the cookie decision"): fix dead-matcher drift and gate the real authoring surfaces, encoding the RESOLVED D2 cookie decision.

## Read first

- The MT-16 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md` and resolved decision **D2**.
- `src/middleware.ts` — current `matcher` (~lines 93-101): `['/', '/editor/:path*', '/api/sites/:path*', '/api/admin/:path*']` — THREE of those four match NO routes on disk. `isEditorHost` (~36-46) reads `EDITOR_HOST`, normalizes host. On `pathname === '/'`: non-editor host → rewrite to `/${HOME_REWRITE_SENTINEL}` (returns BEFORE the cookie check, so anonymous storefront visitors are served); editor-host root → `next()` (un-gated). Cookie gate (~63-80): for matched non-`/` paths, presence-only check of `lumitra_session`, absent → redirect to `${AUTH_BRAIN_URL}/login?return_to=...`.
- `src/middleware.test.ts` — ALREADY encodes the TARGET arrangement (`EDITOR='app.lumitra.co'`); update/extend it for the reconciled routes.
- The REAL route families on disk: `/` (editor), `/projects/*` (editor, landed by MT-09/MT-10), `/preview` + `/projects/<id>/preview` (preview), `(site)/[...slug]` (storefront), `/api/projects/*`, `/api/cms/*`, `/api/commerce/*`, `/api/ai/*`, `/api/health/*`.

## Definition of done

In `src/middleware.ts`:
- Reconcile the `matcher`: gate `/projects/:path*` and the authoring `/api/*` families that need the login bounce; REMOVE the dead `/editor`, `/api/sites`, `/api/admin` entries; keep `/` (the editor-vs-storefront fork). Leave public read/render paths OPEN (the `(site)` catch-all, public `/preview` variants, `/api/health/*`, and the public `/api/cms`+`/api/commerce` READ paths). Choose matcher patterns so writes/editor surfaces are gated but public storefront reads + anonymous order POSTs are NOT bounced.
- On the EDITOR host: an unauthenticated `/projects` (and `/projects/<id>`) bounces to the auth-brain login with a correct `return_to` (the current un-gated `/` exemption must NOT leak to `/projects`).
- Encode **D2 (resolved)**: the `.lumitra.co` apex `lumitra_session` cookie STAYS (suite SSO); do NOT make the editor cookie host-only and do NOT change any auth-brain cookie config. Instead, PUBLISHED-SITE requests must derive tenancy from the HOST and NEVER be authorized by the apex session: on a NON-editor (published) host, the middleware must NOT apply the editor cookie gate (storefront reads + anonymous order POSTs flow through; their route handlers do host-based resolution). The middleware treats the apex session as irrelevant for published-host authz.
- Update/extend `src/middleware.test.ts` so the matcher + gating tests pass with the reconciled routes (editor-host `/projects` bounces unauth; published-host requests are not gated; the dead entries are gone).

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `fix(middleware): reconcile matcher to real routes, gate /projects, encode D2 published-host authz (MT-16)`.

## Constraints

- Stay in this worktree. Files: `src/middleware.ts`, `src/middleware.test.ts`. Do NOT touch the route handlers (they self-guard) or auth-brain.
- Do NOT change `EDITOR_HOST`/`PUBLIC_SITE_BASE_HOST` values or any env (that is Wave 5). The middleware reads `EDITOR_HOST` at runtime; the tests set it.
- Keep `HOME_REWRITE_SENTINEL` import dependency-free (edge runtime; do not pull Prisma/`server-only` into the middleware).
- Do not push to any remote. Output a final completion message.

## Notes

- The middleware cookie gate is a coarse PRESENCE check (no `verifySession` in the edge runtime — cryptographic verify is the route handlers' job, defense in depth). Keep it presence-only.
- D2 is about AUTHORIZATION, not cookie transport: the browser will still send the `.lumitra.co` cookie to `*.sites.lumitra.co`, but the server simply must not use it to authorize published-site/shopper actions. Your job in the middleware: do not gate published-host requests on it.
