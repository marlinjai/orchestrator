---
task: mt-15
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-15** (section "MT-15 - Dedicated (site) layout + storefront 404"): decouple the published storefront (and its 404) from the editor's root layout, which today ships "Create Next App" metadata, `html.light`, and data-table CSS to every storefront and `notFound()`.

## Read first

- The MT-15 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/app/layout.tsx` — the ROOT layout. Note its `metadata` ("Create Next App" title/description), `<html className="light">` (or similar), and the data-table / CMS-grid CSS import(s) (e.g. `cms-grid-theme.css`) + `globals.css`. In the Next App Router, ONLY the root layout can render `<html>`/`<body>`, and it wraps EVERY route — so the storefront currently inherits all of this.
- `src/app/(site)/[...slug]/page.tsx` — the storefront catch-all (the `(site)` route group). `src/app/page.tsx` (`/`, editor) and `src/app/projects/*` (editor dashboard/routes).
- Where the data-table CSS is actually NEEDED: the CMS grid (`src/components/cms/grid/*`). The storefront does not need it.

## Definition of done

- Create `src/app/(site)/layout.tsx`: a layout for the `(site)` route group with per-site metadata hooks (a `generateMetadata` that returns storefront-appropriate metadata — a neutral default now; per-site title/description can be wired from the resolved site later) and NO editor chrome / NO data-table CSS.
- Create `src/app/(site)/not-found.tsx`: a storefront-styled 404 (clean, no editor chrome), so a 404 on a sites host renders the storefront 404, not the editor layout's.
- Make the ROOT layout (`src/app/layout.tsx`) stop styling storefront output: remove the editor-specific "Create Next App" metadata (replace with a neutral/empty default or move it to the editor surface) and move the data-table / CMS-grid CSS import OUT of the root layout to where the editor actually needs it (an editor-side layout or the CMS grid component) so it no longer ships to the storefront. Keep `<html>`/`<body>` + truly-global `globals.css` in the root layout (only the root can own `<html>`).
- The editor (`/`, `/projects/*`) must keep its needed styling (data-table CSS where the grid renders). Do NOT break the editor's appearance.

Test:
- A snapshot/integration test asserts the storefront HTML head no longer contains the editor "Create Next App" metadata (e.g. render the storefront route / its `generateMetadata` and assert the title/description are NOT the editor defaults; or assert the `(site)` layout metadata is used). Assert the storefront 404 renders the `(site)` not-found, not the editor layout.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(site): dedicated (site) layout + storefront 404, decoupled from editor chrome (MT-15)`.

## Constraints

- Stay in this worktree. Files: new `src/app/(site)/layout.tsx`, new `src/app/(site)/not-found.tsx`, `src/app/layout.tsx`, and wherever you relocate the data-table CSS import (a CMS-grid component or an editor layout). Do NOT touch `(site)/[...slug]/page.tsx` (MT-13 owns it) or the render path.
- Prefer the LOW-RISK approach: neutralize root metadata + relocate the data-table CSS, rather than restructuring `/` and `/projects` into a new route group (that risks colliding with MT-09/MT-10/MT-16). Only the root layout, the new `(site)` files, and the CSS-import relocation should change.
- Do not push to any remote. Output a final completion message.

## Notes

- The App Router constraint: only the root layout renders `<html>`/`<body>`. So the decoupling is achieved by making the root layout NEUTRAL (no editor metadata, no editor CSS) and pushing editor-specific styling/metadata down to the editor surface, while `(site)/layout.tsx` adds storefront metadata. The storefront then inherits a neutral root + its own `(site)` layout.
- If `globals.css` contains editor-only rules that bleed into the storefront, that's acceptable to leave for now UNLESS it visibly breaks the storefront — keep scope to metadata + data-table CSS + the 404.
