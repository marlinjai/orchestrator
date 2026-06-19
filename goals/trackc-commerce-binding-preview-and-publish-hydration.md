---
task: trackc-commerce-binding-preview-and-publish-hydration
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-binding-preview-and-publish-hydration.md
depends_on: ["trackc-register-storefront-components-as-bindable-blocks","slice2-publish-read-binding-hydration"]
shared_state: ["hydrate-bindings"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce binding preview parity + gated static-publish hydration (Storefront, Wave 3)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY the `trackc-commerce-binding-preview-and-publish-hydration` spec, nothing more, nothing from other tracks or specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-binding-preview-and-publish-hydration.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Extend `src/lib/renderer/publish/hydrateBindings.ts` (owned by the upstream `slice2-publish-read-binding-hydration` spec): the signature gains a commerce repo via the additive options object, `hydrateBindings(pageTree, pageParams, { cmsRepo, commerceRepo })`. The additive field keeps the existing CMS call site working unbroken.
- Bake ProductList: one block per `ProductDTO` via `commerceRepo.listProducts`, reading the `src/server/commerce` repository DIRECTLY in Node (no HTTP, no React, no jsdom).
- Bake ProductDetail: resolved from `pageParams.handle` via `commerceRepo.getProductByHandle`, again Node-direct against `src/server/commerce`.
- Advisory availability bakes as a DISPLAY value only, carrying the stale/advisory comment. Empty catalog renders empty content; a forced hydration/fetch error renders nothing for that slot and NEVER throws or fails the build.
- HARD LINE: interactive commerce kinds (variant-selector, add-to-cart, cart-view, checkout-button) are NOT baked. They stay as runtime island placeholders, documented and tested as left-untouched.
- New node-project test `src/lib/renderer/publish/__tests__/hydrateBindings.commerce.test.ts`: per-product expansion, detail-from-handle, empty/error path, interactive-not-baked.
- New test `src/lib/renderer/publish/__tests__/parity.commerce.test.ts`: preview-vs-hydrated parity against `HeadlessPageRenderer` for a commerce-bound tree.
- Leave a follow-on stub recording that the publish-pipeline WIRING is gated on the static-html wave (same gate as the CMS hydration spec).

## Hard constraints (do NOT)

- This spec TOUCHES shared state. It is the sole later editor of the `hydrate-bindings` shared file `src/lib/renderer/publish/hydrateBindings.ts`, which is created and owned by the upstream `slice2-publish-read-binding-hydration` dependency. Extend it ONLY via the additive `{ cmsRepo, commerceRepo }` options object; do NOT change the CMS call site behavior, and do NOT touch any other shared state.
- The resolver/hydration path stays React-free and Node-evaluable: read `src/server/commerce` directly in Node, no HTTP, no React, no jsdom in the hydrate path. The commerce test file is a NODE project test (asserted), not jsdom.
- Do NOT bake interactive components. variant-selector, add-to-cart, cart-view, and checkout-button remain client-side runtime islands; baking them is out of scope and a correctness violation.
- Do NOT build the publish-pipeline WIRING (gated on the static-html wave) and do NOT build runtime-island hydration for the interactive components (also static-html wave). Record the gate as a follow-on stub only.
- Do NOT touch MST, the prisma/schema.prisma, the CMS adapter/repo, or any other spec's surface. Do NOT add commerce schema models (those serial prisma-writer specs b2-b6 own `prisma/schema.prisma` and must not run concurrently with another prisma writer; this spec is NOT a prisma writer and must not append to that file). Keep changes minimal and confined to the three files in the spec's "Files and changes" table.
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS). The commerce repo is read directly in Node against whatever the upstream specs provide.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges at Gate B.
- Errors must SURFACE, never be swallowed at the API/contract boundary; the ONLY swallow allowed is the spec's explicit one (a per-slot hydration/fetch error renders nothing for that slot rather than failing the whole build), which must be tested.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.
- Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: `hydrateBindings` extended with `commerceRepo` via the additive options object (CMS call site unbroken); ProductList/ProductDetail bake while interactive kinds stay islands; empty/error handled and never throws; commerce parity test green against `HeadlessPageRenderer`; a follow-on stub records the publish-pipeline wiring is gated on the static-html wave; STATUS row flipped. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
