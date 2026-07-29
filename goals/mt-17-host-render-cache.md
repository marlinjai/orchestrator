---
task: mt-17
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-07, mt-13]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-17** (section "MT-17 - Host-keyed render cache invalidated on publish"): stop doing O(pages) Postgres work + full hydration on every storefront hit. `force-dynamic` + React `cache()` gives ZERO cross-request caching today. MUST come after MT-13 (tenancy correct BEFORE caching, or a cache poisons cross-tenant).

## Read first

- The MT-17 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md` and the resolved PERFORMANCE approach (origin page-cache + Cloudflare CDN edge; this spec is the ORIGIN cache layer).
- `src/app/(site)/[...slug]/page.tsx` — `force-dynamic` + `runtime=nodejs`; wraps `resolvePublishedSite(host)` in React `cache()` (request-scoped dedupe ONLY, not cross-request). Loads ALL pages per hit (MT-13 made it thread `site.workspaceId` into `getCmsRepository`).
- `src/server/sites/publicResolver.ts` — `resolvePublishedSite(host, prisma?, baseHost?)`. `parseSubdomain` gives the subdomain label.
- `src/app/api/projects/publish/route.ts` (returns `subdomain`, landed by MT-07) and `src/app/api/projects/unpublish/route.ts` — the invalidation triggers.
- Next.js `unstable_cache` + `revalidateTag` (App Router). The repo already uses Next 15.

## Definition of done

- Cache the published-site RESOLUTION per host with a tag like `site:<subdomain>`: wrap the host→site resolution (e.g. a `getCachedPublishedSite(host)` around `resolvePublishedSite`) in `unstable_cache`, keyed by the host/subdomain, tagged `site:<subdomain>`. The cache KEY must include the host so cross-tenant bleed is IMPOSSIBLE (tenant-safe by construction).
- Publish and unpublish call `revalidateTag('site:<subdomain>')` so a re-publish is reflected on the next request. Publish has the `subdomain` (from `ensureSiteDomain`); unpublish resolves the site's subdomain (its `SiteDomain` row survives — look it up) to revalidate the same tag.
- Where feasible, load/hydrate only the MATCHED page snapshot per request rather than ALL pages for every hit (the resolver currently selects all pages; if a clean narrowing is available, do it; otherwise cache the all-pages resolution so the DB work happens once per publish, not per request).
- Tenant-safe: the cache key includes the host, so a cached entry can never serve another tenant's content.

Test:
- Publish → a request renders the new content; a second identical request does NOT re-run the DB read (cache hit — assert via a spy/mock call count on the prisma read or the resolver); unpublish/republish invalidates correctly (after `revalidateTag`, the next request re-reads). Caching is asserted tenant-safe (two hosts → two cache entries, no bleed).

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `perf(render): host-keyed published-site cache invalidated on publish/unpublish (MT-17)`.

## Constraints

- Stay in this worktree. Files: `src/app/(site)/[...slug]/page.tsx` (or a new `src/server/sites/cachedResolver.ts`), `src/app/api/projects/publish/route.ts`, `src/app/api/projects/unpublish/route.ts`, tests. Do NOT change the tenancy threading (MT-13 owns it) — only ADD caching around the already-correct resolution.
- Do NOT cache anything that would defeat tenancy: the key MUST include the host. Dynamic commerce/cart islands stay client-side and uncached (they call the origin live).
- Do not push to any remote. Output a final completion message.

## Notes

- `unstable_cache` callbacks must be serializable-friendly; the resolved `PublishedSite` is plain data (good). Keep the prisma client OUT of the cached function's closure args (construct it inside or pass only the host string as the cache key input).
- The whole point: build the page once, serve the saved resolution to all later visitors until re-publish. The Cloudflare CDN (Wave 5) fronts this; the origin cache is this spec.
