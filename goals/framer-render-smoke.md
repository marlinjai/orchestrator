---
task: framer-render-smoke
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build && pnpm test:integration
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal

Prove the published-site SSR render chain works END TO END against a REAL Postgres with REAL seeded
data, as a PERMANENT integration test (a `.itest.ts`). Today the whole render chain
(resolve -> snapshot adapt -> hydrate -> render) is covered only by unit tests with MOCKED repos; it has
NEVER executed against a real database with real CMS + commerce rows. This task closes that gap and
leaves behind a permanent CI smoke (the integration suite already runs in CI via the `verify` workflow)
plus a reusable demo-seed helper for the prod flash session.

This is a real smoke: if it surfaces a genuine bug in the merged render/resolve/hydrate code (PRs
#37-#41), FIX it production-grade. Do NOT weaken an assertion to make a red smoke go green.

## What to build

1. **A reusable demo-seed helper** (e.g. `src/lib/renderer/server/__tests__/seedDemoSite.ts`, exported
   so a thin `scripts/seed-demo.ts` wrapper can reuse it against a live `DATABASE_URL` for the prod
   demo). Given a `PrismaClient`, it seeds a coherent demo:
   - **Commerce catalog**: 2 products, each with options/variants + a `price` (integer minor units) +
     `inventory_item`/`inventory_level` with real stock. Crib the exact shapes from
     `src/server/commerce/repository/__tests__/catalog.itest.ts` and `read.test.ts`.
   - **CMS collection**: one `dt_*` collection (e.g. "Events") with 3 rows whose titles are
     assertable strings. Seed via the same path `getCmsRepository()` reads
     (`src/server/cms/`), so `listRows` returns them. Crib from the CMS adapter / existing CMS tests.
   - **A published `Site` + a `SitePage`** whose `snapshot` is a valid `PageModel` SnapshotOut for a
     HOME page (slug empty/`home`). The page's `appComponentTree` must contain: a CMS **Collection**
     block bound to the Events collection (read binding + a `query` object), a **ProductList** bound to
     the catalog, a **ProductDetail**, and the 4 interactive commerce islands (`variant-selector`,
     `add-to-cart`, `cart-view`, `checkout-button`). Use the exact `ComponentNode`/snapshot shapes from
     the existing render unit-test fixtures (`snapshotToComponentNode.test.ts`,
     `renderPublishedPage.test.ts`, `renderComponentNode.test.tsx`) so the tree is valid and
     hydrateBindings expands it. Stamp `workspace_id` + `tenant_group_id` on the rows.
   - **A `SiteDomain`** with `subdomain: 'demo'` pointing at the site.
   - **A second DRAFT `Site`** (status not published) with its own `SiteDomain` subdomain, to prove the
     published-only filter.

2. **The smoke `.itest.ts`** (e.g. `src/lib/renderer/server/__tests__/renderPublishedPage.itest.ts`).
   Use the shared integration Postgres: the `vitest.integration.setup.ts` globalSetup already boots a
   container and runs `prisma migrate deploy`, exposing `process.env.DATABASE_URL`. In `beforeAll`,
   construct a `PrismaClient` on that URL and call the seed helper. Then exercise the REAL chain (NO
   mocks):
   - `resolvePublishedSite('demo.<base>')` -> the seeded site (set `PUBLIC_SITE_BASE_HOST` or use a
     three-label host so `parseSubdomain` yields `demo`).
   - `snapshotToComponentNode(page.snapshot)` -> the ComponentNode root + metadata.
   - `hydrateBindings(root, params, { cmsRepo: getCmsRepository(), commerceRepo: getCommerceServerRepository() })`
     against the REAL repos hitting the seeded DB.
   - `renderToStaticMarkup(<the React tree from renderComponentNode(hydrated)>)` -> an HTML string
     (the 4 islands are `'use client'` components; `renderToStaticMarkup` renders their initial markup
     server-side, which is what you assert on).

3. **Assertions** (the high-signal proofs):
   - `resolvePublishedSite` returns the seeded published site for `demo.<base>`; returns `null` for an
     UNKNOWN subdomain; returns `null` for the seeded DRAFT site's subdomain (published-only).
   - `matchPageBySlug(['__home'])` (the `HOME_REWRITE_SENTINEL`) resolves the same home page as empty
     segments.
   - The rendered HTML CONTAINS every seeded Events row title (proves CMS Collection hydration on real
     data) and every seeded product title (proves commerce ProductList hydration on real data).
   - The 4 interactive island kinds each appear in the output (assert on a stable island marker, e.g.
     the `CommerceIsland` wrapper attribute / data-component-kind; inspect `CommerceIsland.tsx` for the
     stable hook to assert on).
   - An empty/unbound data slot degrades gracefully (no throw) if you include one.

## Read first

- `src/server/sites/publicResolver.ts` (`resolvePublishedSite`, `parseSubdomain`, `matchPageBySlug`,
  `HOME_REWRITE_SENTINEL`), `src/lib/renderer/server/snapshotToComponentNode.ts`,
  `src/lib/renderer/server/renderComponentNode.tsx`, `src/lib/renderer/server/renderPublishedPage.tsx`,
  `src/lib/renderer/server/CommerceIsland.tsx`, `src/lib/renderer/publish/hydrateBindings.ts`.
- The render unit tests for the valid snapshot/ComponentNode shapes:
  `src/lib/renderer/server/__tests__/{snapshotToComponentNode,renderPublishedPage,renderComponentNode}.test.*`.
- `vitest.integration.setup.ts` (the shared PG + DATABASE_URL contract) and an existing `.itest.ts`
  (`src/server/commerce/repository/__tests__/catalog.itest.ts`) for the seeding + container pattern.
- `src/server/commerce/repository/read.ts` (`getCommerceServerRepository`) + `read.test.ts` fixtures,
  and `src/server/cms/` (`getCmsRepository`, the dt_* seeding path) + `src/models/PageModel.ts`.

## Definition of done

- The new `.itest.ts` passes under `pnpm test:integration` and asserts everything above against a real
  Postgres. The seed helper is factored + reusable (plus a thin `scripts/seed-demo.ts` wrapper that
  seeds against a live `DATABASE_URL`, for the prod demo).
- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build && pnpm test:integration` all green.
- If a REAL render/resolve/hydrate bug surfaced, it is FIXED in the merged code (describe it in the
  completion message); if nothing broke, say so explicitly (that is the smoke passing).
- Single commit, conventional-commit message describing the WHY.

## Constraints

- No `prisma/schema.prisma` change, no migration (seed against the existing schema). If a real bug needs
  a schema change, STOP and escalate.
- Do NOT weaken or skip any existing test, and do NOT make the new smoke pass by asserting less than the
  real-data proofs above. The point is to catch what the mocks hid.
- `.itest.ts` suffix so it runs ONLY under `pnpm test:integration` (never the headless `pnpm test`).
  It requires Docker (testcontainers); the verify env has it.
- No em-dashes or en-dashes anywhere. Stay in this worktree; do not push to any remote (the operator
  handles PR + merge). When done, output a final completion message: what the smoke asserts, whether it
  surfaced/fixed any real bug, and the files changed.

## Notes

- This is the highest-value verification of the render layer + a permanent regression guard + the demo
  seed the prod flash session needs. Three deliverables from one test.
- If `renderToStaticMarkup` on a `'use client'` island throws server-side (hooks/context), inspect how
  `renderPublishedPage.tsx` / the route already mounts islands and mirror that (the islands may need a
  provider wrapper or may render a static placeholder server-side); assert on whatever stable server
  output the island produces, do not force client behavior server-side.
