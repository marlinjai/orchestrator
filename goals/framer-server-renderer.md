---
task: framer-server-renderer
spec: docs/specs/build-2026-06/hosted-demo/hosted-page-demo.md
depends_on: [framer-commerce-read-repo]
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Build the **SSR-on-request render layer**: the public route that resolves a published site from the
request Host, loads its persisted `SitePage` snapshot, hydrates CMS + commerce data LIVE per request,
renders the primitive tree to HTML server-side, and emits the 4 interactive commerce kinds as client
islands. This is build items #4-#6 (+ #8 analytics injection) of the hosted-page demo plan, RECONCILED
to the P1 foundation. Render mode is LOCKED to SSR-on-request (NOT static export — do not relitigate).

`framer-commerce-read-repo` (the read repo this consumes) is already MERGED to main; this worktree is
cut from that main, so `getCommerceServerRepository()` is present.

## Architecture (grounded in a code map — follow it)

The hard data-expansion already exists (`src/lib/renderer/publish/hydrateBindings.ts`, PURE, never
called). So the new renderer is a tree-walk over already-expanded primitives + island emission, NOT a
port of the client renderers. Build these pieces:

1. **snapshot -> ComponentNode adaptor.** A `SitePage.snapshot` is a full `PageModel` SnapshotOut
   (`src/models/PageModel.ts`): its `appComponentTree` field is the renderable root (a `ComponentModel`
   SnapshotOut), and `canvasNodes` holds viewports/floating elements (NOT rendered on the published
   page). Write a pure adaptor that extracts `appComponentTree` and maps it to the
   `ComponentNode { type, props?, bindings?, children?, id? }` shape `hydrateBindings` expects. Verify
   the field alignment between the `ComponentModel` SnapshotOut and `ComponentNode` (type / props /
   bindings / children / id) and map faithfully; the page's `metadata` (title, description, og*) feeds
   SEO.

2. **`ServerComponentRenderer`** (`src/lib/renderer/server/`, NEW). A pure, SSR-safe tree-walk over the
   HYDRATED `ComponentNode` tree (the output of `hydrateBindings`). For each node:
   - If `props['data-component-kind']` is one of the 4 INTERACTIVE commerce kinds
     (`variant-selector`, `add-to-cart`, `cart-view`, `checkout-button`): emit the EXISTING client
     island component from `src/lib/renderer/commerce/*` (`VariantSelector` / `AddToCartButton` /
     `CartView` / `CheckoutButton`), passing the node's resolved props. These hydrate client-side.
   - Otherwise: map `node.type` -> HTML tag via the SERVER-importable `COMPONENT_REGISTRY`
     (`src/lib/componentRegistry.ts`, a pure data module: each entry has `htmlType`). Emit a React
     element (`React.createElement(htmlType, props, children)`) with resolved props/style. Do NOT read
     `window.__componentRegistry` (the client dispatch path in `createComponentElement.tsx`); it does
     not exist server-side. No MST, no `observer()`, no hooks.
   - Unknown node types degrade GRACEFULLY (render nothing / a harmless wrapper), never throw.

3. **Client island shell** (`'use client'`). The 4 islands consume `useCommerceDataSource()`
   (`src/lib/commerce/context.tsx`) and any selection context. Mount a client provider wrapping the
   island region with `CommerceDataSourceContext.Provider value={getSharedHttpCommerceDataSource()}`
   (mirror `src/components/preview/PreviewShell.tsx` lines ~99-100) so the islands hit same-origin
   `/api/commerce/*` reads and checkout POSTs to `/api/commerce/orders` (stops at order-created). Keep
   the binding scope the islands re-resolve (`{{variant.*}}` / `{{availability.*}}`) intact.

4. **Public RSC route** `src/app/(site)/[[...slug]]/page.tsx` (server component):
   - Resolve the site from the request Host server-side (via `headers()`), NOT a middleware rewrite.
     The P1 `src/middleware.ts` is an AUTH gate only (matcher `/editor`, `/api/sites`, `/api/admin`) and
     leaves public render paths open; do NOT modify it to add host-routing. Write a NEW resolver (e.g.
     `src/server/sites/publicResolver.ts`) that parses the subdomain from Host, looks up
     `SiteDomain` by `subdomain` (the P1 model: `subdomain` unique, `customHostname` unique, `siteId`,
     `verificationStatus`, `isPrimary`), and loads the matched published `Site` + `SitePage` rows
     DIRECTLY via Prisma. This is a PUBLIC, anonymous read keyed by subdomain (NOT workspace-scoped:
     the subdomain identifies the site). Serve ONLY published sites; a draft/unknown subdomain -> 404.
   - Resolve the page by the catch-all `slug` (root slug -> the home page); extract dynamic route params
     (`id` / `handle`) from the slug for RecordView / ProductDetail.
   - Call `hydrateBindings(componentNode, pageParams, { cmsRepo: getCmsRepository(), commerceRepo:
     getCommerceServerRepository() })`. Both repos are server-only and already on main.
   - Render the hydrated tree via `ServerComponentRenderer`. Emit SEO/OG from the page `metadata`
     (`generateMetadata` or inline `<head>` per Next App Router).
   - A missing site OR missing page -> Next `notFound()` (404). Errors surface (loud), never a blank 200.

5. **Analytics injection (#8).** Inject the analytics tracker `<head>` snippet when the snapshot's
   Lumitra binding is `enabled`. SALVAGE the already-built, tested `trackerSnippet.ts` from the
   preserved branch rather than rewriting it: retrieve it with
   `git show orchestrator/framer-p2-publish:src/lib/renderer/publish/trackerSnippet.ts`
   (and its test `...:src/lib/renderer/publish/__tests__/trackerSnippet.test.ts`) and add those files to
   THIS slice. It builds `window.__AP_CONFIG` / `window.__AP_VARIANTS` and embeds ONLY the public
   `ap_live_` key (it REFUSES a secret-shaped key as a backstop). Resolve the public ingestion key
   server-side from the snapshot's `apiKeyRef` (server-side ref -> literal `ap_live_` key); NEVER put the
   `apiKeyRef` secret literal in the artifact. For the demo, A/B is deferred, so pass `variants: {}`
   (control baseline). Gate injection on `lumitra.enabled`; when disabled, inject nothing.

## Read first

- `docs/specs/build-2026-06/hosted-demo/hosted-page-demo.md` (items #4-#6, #8, "The one risk, verified",
  Test plan). Note item #1's `PublishedSite` name is SUPERSEDED by P1 `Site`/`SitePage`.
- `src/lib/renderer/publish/hydrateBindings.ts` (the function you call: signature, the `ComponentNode`
  shape, the 4 interactive kinds left verbatim, the empty/error contract).
- `src/lib/componentRegistry.ts` (`COMPONENT_REGISTRY`, `htmlType`, `dataComponentKind`) — your
  server-side primitive map. `src/lib/renderer/createComponentElement.tsx` (the CLIENT dispatch — read
  it to mirror prop/style handling, but do NOT reuse its `window.__componentRegistry` path).
- `src/models/PageModel.ts` (`PageSnapshotOut`, `appComponentTree`, `canvasNodes`, `metadata`, `slug`).
- `src/lib/renderer/commerce/{VariantSelector,AddToCartButton,CartView,CheckoutButton}.tsx`,
  `src/lib/commerce/context.tsx` (`useCommerceDataSource`, `CommerceDataSourceContext`),
  `httpCommerceDataSource.ts` (`getSharedHttpCommerceDataSource`), and
  `src/components/preview/PreviewShell.tsx` (how the providers are mounted for a rendered page).
- `src/server/cms/` (`getCmsRepository`, `CmsReadRepository`) and
  `src/server/commerce/repository/read.ts` (`getCommerceServerRepository` — just merged).
- `prisma/schema.prisma` `SiteDomain` / `Site` / `SitePage` models. `src/server/sites/snapshot.ts`
  (the `PersistedPage.snapshot` shape you read). `src/app/preview/page.tsx` (the closest existing render
  route; client-only — yours is server-side). Check the existing `src/app/` route tree so the new
  `(site)/[[...slug]]` catch-all COEXISTS with `/editor`, `/preview`, `/api` (Next gives specific routes
  precedence over an optional catch-all) and does NOT clobber an existing root `app/page.tsx` if one
  exists.

## Definition of done

- The public route renders a seeded published page server-side with LIVE CMS + commerce data hydrated
  per request, emits the 4 islands as client components, injects SEO/OG + the analytics snippet (when
  enabled), and 404s on a missing site/page.
- `ServerComponentRenderer` + the snapshot->ComponentNode adaptor + the public resolver are pure,
  SSR-safe, and unit-tested headless (`.test.ts(x)`), per the demo plan Test plan:
  - adaptor: a `PageModel` SnapshotOut -> the expected `ComponentNode` tree.
  - renderer: a hydrated primitive tree -> expected HTML; each of the 4 interactive kinds emits its
    island marker/component; unknown node types degrade with no throw.
  - public route: given a seeded `SitePage` (fake repo set), resolves + hydrates + returns HTML
    containing the CMS/commerce data; a missing site -> 404.
  - resolver: subdomain -> site; unknown subdomain -> 404/null; only published sites served.
  - `trackerSnippet`: enabled binding injects the snippet with the public key; disabled -> none; the
    non-public-key backstop still refuses a secret-shaped key (the salvaged test covers this).
- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all green.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- SSR-on-request only. NO static export, NO `renderToStaticMarkup` of MST, NO porting the client
  renderers. The server renderer walks the already-hydrated `ComponentNode` tree.
- Server owns money + stock; the 4 islands stay client-authoritative; advisory availability is
  display-only and NEVER permission to sell.
- Do NOT modify `src/middleware.ts` (it is the auth gate; the public route is outside its matcher). Do
  NOT touch `prisma/schema.prisma` or add a migration (the P1 `SiteDomain`/`Site`/`SitePage` models
  suffice) — this keeps the slice parallel-safe with the prisma-holding content-agent slice. Do NOT edit
  `src/server/sites/repository.ts` or its barrel (the parallel `framer-publish-write` slice owns those);
  add your public resolver as a NEW file and import Prisma directly.
- Studio design tokens; reuse `src/components/ui/*`. Production-grade: cover unhappy paths (unknown
  subdomain, missing page, empty collection, unbound data node, draft site). Errors surface loudly. Zero
  tech debt: fix in-scope follow-ups in this PR; file genuinely out-of-scope items as `open_thread`.
- No em-dashes or en-dashes anywhere (code, comments, commit message). The salvaged `trackerSnippet.ts`
  is already clean; keep it so.
- Stay in this worktree. Do not push to any remote (operator handles PR + merge). Do not run destructive
  commands. When done, output a final completion message listing files changed (incl. the salvaged
  trackerSnippet files).

## Notes

- This pairs with `framer-publish-write` (the WRITE side, running in parallel): publish writes
  `SitePage` snapshots; you READ them. You share the `snapshot.ts` contract via main, not each other's
  code, so keep your files disjoint from that slice (new files + direct Prisma reads; never edit
  `repository.ts`/`index.ts` barrel).
- The islands' client data source + checkout already exist and hit `/api/commerce/*`; your job is to
  MOUNT them correctly on the published page (the provider shell), not rebuild them.
- Real file/image storage (Storage Brain/R2) is a separate later task; if the snapshot references an
  upload URL, render it as authored (do not attempt to bundle/upload assets here).
