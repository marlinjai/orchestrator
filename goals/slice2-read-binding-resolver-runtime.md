---
task: slice2-read-binding-resolver-runtime
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-read-binding-resolver-runtime.md
depends_on: [track0-backend-foundation]
shared_state: ["vitest-config"]
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone read-binding resolver runtime (slice2, CMS content tier wave 1)

This is part of the framer-clone build (CMS content tier, wave 1). Build EXACTLY the slice2-read-binding-resolver-runtime spec, nothing more, nothing from other slices or tracks. This slice depends ONLY on Track 0 (for the vitest `projects` substrate it consumes); it launches after Track 0 has MERGED.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-read-binding-resolver-runtime.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/bindings/resolver/expression.ts`: `parseExpression` + `evaluateExpression`. Mustache-style `{{path.segments}}` ONLY. Single-segment `{{title}}` resolves against the innermost row frame; multi-segment `{{row.title}}`, `{{collection.name}}`, `{{page.params.id}}`. No JS expressions, no filters, no method calls (return `null` for `{{a + b}}`). Returns `undefined` and NEVER throws on unknown paths.
- `src/lib/bindings/resolver/scope.ts`: `BindingScope`, `BindingFrame`, `pushRowFrame`, `pushCollectionFrame`, `lookup` (returns `undefined` on miss, never throws).
- `src/lib/bindings/resolver/applyBindings.ts`: PROVIDER-FREE `applyBindings(node, baseProps, scope)` (callers feed already-fetched rows). Merges the resolved value into `props.children` for Text nodes and into `style.X` for dot-path slots; returns `isLoading:true` when any slot is `LOADING_SENTINEL`. Memoize per (binding, scope-snapshot) within a render pass. This SUPERSEDES the wave-2 `applyBindings(node, props, scope, dataSource)` signature.
- Tests under `src/lib/bindings/resolver/__tests__/` (node project): `expression.test.ts` (parse + lookup) and `applyBindings.test.ts` (merge + isLoading + node-env identical-output assertion).
- The whole `src/lib/bindings/resolver/*` module MUST have ZERO React imports (grep/lint check) so the static-publish path can evaluate bindings in Node at build time.
- Touchpoints are read-only references: `src/lib/bindings/types.ts` (ReadBinding), `dataSource/types.ts` (Collection/Row). Do not restructure them.

## Shared state: vitest-config (additive only)

This slice declares `vitest-config` as its ONLY shared state. Because this slice now `depends_on: [track0-backend-foundation]`, Track 0 (the SOLE owner of the `vitest.config.ts` `projects` migration) has already MERGED before this slice launches. So this slice ONLY ADDS its resolver test glob to Track 0's existing node project (additive, no restructure, no migrate branch). Do NOT re-do the `projects` migration: it already exists. Just register `src/lib/bindings/resolver/**` under the node project if Track 0 did not already include it.

## Hard constraints (do NOT)

- Do NOT wire the renderer (the data-components spec owns ComponentRenderer/HeadlessComponentRenderer scope threading). Do NOT add commerce scope frames `pushProductFrame`/`pushVariantFrame`/`pushAvailabilityFrame` (Track C `trackc-commerce-binding-scope-frame-and-resolver` extends THIS module later). Do NOT build write bindings.
- The resolver MUST stay React-free and Node-evaluable: no React import anywhere in `src/lib/bindings/resolver/*`, no provider coupling, no `dataSource` argument on `applyBindings` (callers feed already-fetched rows). No doc-tier-core coupling.
- Do NOT touch shared state owned by another slice beyond this slice's declared `vitest-config`. Do NOT touch `prisma/schema.prisma`, MST, the lockfile, or `next-config`. Keep changes minimal and confined to `src/lib/bindings/resolver/*` plus the `vitest.config.ts` edit.
- Regression: the existing 16-test drag suite plus the wave-1 bindings tests must stay green under the `projects` config; the jsdom project stays unchanged for `src/**`.
- Errors must SURFACE, never be swallowed, EXCEPT where the spec mandates non-throwing behavior (`lookup`/`evaluateExpression` return `undefined`/`null` on miss by contract). Do not silently swallow real failures elsewhere.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch ONLY. A human reviews and merges at Gate B.
- Secrets via Infisical only, never `.env`, never a literal. No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section: resolver lands with NO React import (enforced by test/lint), parser plus lookup plus applyBindings tests pass under the node project, memoization per (binding, scope-snapshot) within a render pass, the resolver glob is registered under Track 0's existing `projects` node env with the existing jsdom suite green (regression asserted), and the STATUS row flipped. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
