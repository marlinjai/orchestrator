---
task: framer-root-routing
shared_state: [next-config]
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Serve the published storefront HOME at the host root `/` on a published-site host, while keeping `/` on
the editor host as the editor. This closes the open thread from the server-renderer slice (PR #40):
the public route is a REQUIRED catch-all `app/(site)/[...slug]/page.tsx`, so it matches `/about` and
`/products/x` but NOT bare `/`; and Next is host-agnostic, so today `/` is the editor (`app/page.tsx`)
on EVERY host. We disambiguate `/` by HOST in the existing middleware.

## The host model (decided with Marlin, 2026-06-25)

- The **editor** is ALWAYS served on a single fixed lumitra-owned host (an env var `EDITOR_HOST`, e.g.
  `app.lumitra.co`).
- A **published site** is served on any OTHER host (for this demo: a `*.<base>.lumitra.co` subdomain;
  custom domains are a separate later roadmap item, out of scope here).
- So the discriminator is simply: **is the request Host the editor host?** Editor host -> editor and the
  existing auth gate. Any other host -> the storefront, including its root `/`.

## What to build

1. **Edit `src/middleware.ts`** (this slice is explicitly allowed to modify it; the prior
   "do not touch middleware" constraint was for the parallel batch, which is now merged). Add an
   editor-host-aware root rule AHEAD of the existing auth-bounce logic, and add `/` to the matcher.
   Required shape:

   ```ts
   const EDITOR_HOST = process.env.EDITOR_HOST;
   const host = (request.headers.get('host') ?? '').split(':')[0].toLowerCase();
   // Dev / unconfigured safety: with no EDITOR_HOST, or on localhost, treat EVERYTHING as the editor
   // host so `/` stays the editor and local dev is unchanged. The rewrite only activates in prod where
   // EDITOR_HOST is set and the request Host differs.
   const isEditorHost =
     !EDITOR_HOST || host === EDITOR_HOST.toLowerCase() ||
     host === 'localhost' || host === '127.0.0.1';

   if (request.nextUrl.pathname === '/') {
     if (!isEditorHost) {
       // Published-site root -> storefront home. rewrite (NOT redirect): the URL stays `/`.
       return NextResponse.rewrite(new URL('/__home', request.url));
     }
     // Editor host root: preserve EXACTLY today's behavior (NOT auth-bounced; the editor loads and
     // owns its own auth). Do NOT start gating `/`.
     return NextResponse.next();
   }
   // ...existing auth-bounce logic for /editor, /api/sites, /api/admin unchanged below...
   ```

   And extend `config.matcher` to include `'/'` (so the middleware runs on root) WITHOUT removing any
   existing matcher entry. CRITICAL: a published-site visitor is anonymous and must NEVER be bounced to
   the auth-brain login; the root rewrite returns BEFORE the cookie check, so anonymous site-root
   traffic is served, not bounced.

2. **Teach the storefront resolver to treat the home sentinel as the home request.** The rewrite sends
   `/__home`, so the `[...slug]` route receives `slug = ['__home']`. In
   `src/server/sites/publicResolver.ts` `matchPageBySlug`, recognize a single `__home` segment as the
   HOME request (equivalent to empty segments -> the page whose slug is empty / `index` / `home`).
   Define the sentinel as an exported constant (e.g. `HOME_REWRITE_SENTINEL = '__home'`) and import it
   in the middleware so the two never drift. A real published page can never legitimately use `__home`
   as a slug (reserved), but guard against it anyway (the sentinel resolves home, not a page literally
   slugged `__home`).

3. **Env contract.** Add `EDITOR_HOST` to `.env.example` with a comment (the fixed lumitra editor host;
   unset in dev so `/` stays the editor). No secret; a plain hostname.

## Read first

- `src/middleware.ts` (the existing auth gate: matcher, the `lumitra_session` cookie bounce, the
  edge-runtime note). Your change must keep that logic intact for `/editor`, `/api/sites`, `/api/admin`.
- `src/server/sites/publicResolver.ts` (`matchPageBySlug`, the home-alias handling you extend, and the
  `parseSubdomain` -> `resolvePublishedSite` flow the rewrite ultimately feeds).
- `src/app/(site)/[...slug]/page.tsx` (the route the rewrite targets; confirm `/__home` flows through
  `params.slug = ['__home']` -> resolver -> home page).
- `src/app/page.tsx` (the editor at `/`, client-only) so you confirm the editor-host `/` path is
  unchanged.

## Definition of done

- On a non-editor host, `GET /` rewrites (URL unchanged) to the storefront home and renders it
  (404 if that site has no home page). On the editor host (or localhost / unset EDITOR_HOST), `GET /`
  is the editor exactly as today. `/editor`, `/api/sites`, `/api/admin` auth-bounce behavior is
  unchanged.
- Headless tests: middleware rewrites a non-editor-host `/` to the sentinel and does NOT bounce it to
  login; editor-host `/` (and localhost `/`) returns `next()` (no rewrite, no bounce); an unauthenticated
  `/editor` still bounces to the auth-brain login; `matchPageBySlug(['__home'])` resolves the same page
  as the empty-segments home request; a non-home path still matches/404s as before. Follow the repo's
  existing middleware/resolver test patterns.
- `.env.example` documents `EDITOR_HOST`.
- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all green.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Do NOT change the storefront route from a required `[...slug]` to an optional `[[...slug]]` (that
  re-introduces the `/` collision with `app/page.tsx` and is a Next build error). The host-rewrite is
  the deliberate mechanism.
- Do NOT move or restructure the editor route, and do NOT start auth-gating the editor `/` (preserve
  today's behavior precisely).
- No `prisma/schema.prisma` change, no migration. Custom-domain (`SiteDomain.customHostname`) resolution
  is OUT OF SCOPE (a separate roadmap item); this slice is subdomain/editor-host routing only.
- SSR-on-request stays the model. No em-dashes or en-dashes anywhere.
- Stay in this worktree. Do not push to any remote (the operator handles PR + merge). When done, output a
  final completion message listing files changed.

## Notes

- `rewrite` not `redirect`: the visitor must keep seeing `demo.<base>.lumitra.co/`, not be sent to a
  `/__home` URL. Verify the rewrite preserves the original URL.
- Keep the editor host fully isolated from the storefront: on a site host, `/editor` etc. simply fall
  through to the `[...slug]` route and 404 as a non-existent published page (the editor is never exposed
  on a published-site host). That is the desired behavior; no extra work needed.
