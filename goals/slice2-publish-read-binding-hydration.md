---
task: slice2-publish-read-binding-hydration
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-publish-read-binding-hydration.md
depends_on: ["slice2-read-only-data-components","slice2-data-loading-empty-error-states","slice2-cms-server-adapter-and-repo"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone read-binding hydration in preview + (gated) static publish

This is part of the framer-clone build (cms-content-tier track, wave 3). Build EXACTLY the slice2-publish-read-binding-hydration spec, nothing more, nothing from other specs or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-publish-read-binding-hydration.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/renderer/publish/hydrateBindings.ts` (new): a reusable build-time hydration helper that expands a data-bound tree via the React-free resolver (`applyBindings` / `pushRowFrame`) into concrete prop values. Runs in Node (no React, no jsdom).
- Options-object signature: `hydrateBindings(pageTree, pageParams, { cmsRepo })` returning `Promise<ComponentNode>`, so Track C can later add `{ cmsRepo, commerceRepo }` additively without breaking this call site.
- Read rows server-side by importing the local `src/server/cms` `CmsReadRepository` DIRECTLY (NOT a React hook, NOT `/api/cms` over HTTP). This is the build-time direct-import reader; the live client provider keeps reading `/api/cms/*` and is unchanged.
- Behavior: Collection expands to one block per row with `{{row.field}}` values baked in (no LOADING text); RecordView resolves from the page slug params; empty collection yields the configured `emptyContent`; a fetch error renders nothing for that slot and NEVER throws the build.
- `src/lib/renderer/publish/__tests__/hydrateBindings.test.ts` (new, node project): per-row expansion, empty case, forced-error case, asserting it runs under the resolver-runtime node-env config.
- `src/lib/renderer/publish/__tests__/parity.test.ts` (new): the hydrated tree's text content matches the `HeadlessPageRenderer` preview render of the same bound tree.
- A clear TODO plus a follow-on spec stub recording that wiring `hydrateBindings` into the publish pipeline is GATED on the static-html wave.

## Hard constraints (do NOT)

- Do NOT import `@marlinjai/doc-tier-core` anywhere; the helper reads the local `src/server/cms` `CmsReadRepository` directly, doc-tier-core stays dropped.
- Do NOT wire `hydrateBindings` into `projectPublisher.ts` or the per-page emitter; those files do NOT exist yet and the wiring is GATED on the static-html wave (`static-html-spike`, `static-html-publish-pipeline`). Build the reusable helper plus the parity assertion only, so wave-pickup is a one-line call.
- Do NOT build Track C commerce hydration; that spec (`trackc-commerce-binding-preview-and-publish-hydration`) EXTENDS this helper's signature later.
- Do NOT build client-side runtime island hydration (separate wave-3 surface).
- Keep the resolver React-free and Node-evaluable: `hydrateBindings` and its node-project test must run with no React and no jsdom, under the resolver-runtime node-env vitest config.
- Do NOT touch the MST tree or any shared state; this spec declares `sharedState: []` and `touchesSharedState: false`, so add no new MST surface and do not modify state owned by another spec.
- Do NOT change the preview path: preview mode keeps the live polling provider from `slice2-prisma-datasource-provider`, unchanged.
- Keep changes minimal and scoped to the three files in the spec's table; do not build other specs' surface.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges at Gate B.
- Errors must surface, never be swallowed: the only swallow allowed is the spec's documented one (a fetch error during hydration renders nothing for that slot and does not throw the build), and that path must be covered by a test.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: `hydrateBindings` lands with the options-object `{ cmsRepo }`, runs in Node, never throws on empty/error; NO `@marlinjai/doc-tier-core` import; the parity test is green against `HeadlessPageRenderer`; a clear TODO plus follow-on spec stub records the publish-pipeline wiring is gated on the static-html wave; STATUS row flipped. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
