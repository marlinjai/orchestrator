---
task: deck-core-phase-a
spec: plans/2026-05-31-deck-core-phase-a-kickoff.md
---

# Goal

Build the render pipeline of `deck-core`, arbosano-local, framework-free and MST-free, proven by byte-reproducing the shipped `public/deck/index.html` from a `DeckSnapshot` of its 16 slides. This is one PR on branch `feat/deck-core-phase-a`. Four deliverables:

1. A `DeckSnapshot` data model (plain TypeScript + Zod, no mobx).
2. `renderDeck(snapshot, tokensCss): string` that emits reveal.js HTML.
3. `themeToTokensCss(tokens): string` that emits the frozen `--c-*` / `--surface-*` / `--font-*` / `--tracking-*` contract from structured tokens.
4. A `pnpm deck` CLI: deck JSON in, reveal.js HTML out.

Your authoritative spec is `plans/2026-05-31-deck-core-phase-a-kickoff.md` in this worktree. Read it in full first. This goal file summarizes it; the kickoff doc governs where they appear to differ.

## Read first (in this order)

1. **Your spec**: `plans/2026-05-31-deck-core-phase-a-kickoff.md` (in this worktree). Read every line, especially "Decided defaults", "Gotchas (load-bearing)", and "Out of scope".
2. **The byte-target, THE source of truth**: `public/deck/index.html` (589 lines) and `public/deck/theme.css` (654 lines) in this worktree. Read both fully. This shipped deck is verified-working; you are reproducing IT, not the skill recipe.
3. **The parent spec** (read sections 2 and 4.1 for the token schema + data model rationale): absolute path `/Users/marlinjai/software-dev/knowledge-base/research/2026-05-31-revealjs-ai-deck-authoring-tool.md`. If you cannot read outside this worktree, proceed: the kickoff doc already distills the decided defaults and the data model.
4. **The skill** (read for the WHY behind each CSS rule, NOT as the recipe; it diverges from the shipped deck): absolute path `/Users/marlinjai/.claude/skills/arbosano-revealjs/SKILL.md`. When in doubt, the shipped deck wins.
5. **Render-dispatch pattern to mirror** (dispatches a recursive node tree by type; we do the same shape but EMIT STRINGS, not React elements): absolute path `/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/src/lib/renderer/createComponentElement.tsx`.
6. **CLI pattern to copy** (hand-rolled arg parse, no commander): absolute path `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-studio/src/cli/generate.ts`.

## Decided defaults (do NOT re-litigate)

- **hex-as-authored for v1.** Carry the skill's exact hex values. Do not re-author in OKLCH yet. Keep a `hex` field on the color type so OKLCH is a non-breaking upgrade later.
- **Commit generated CSS** plus a CI "do not hand-edit" check (the deck ships as a static asset, no build step at serve time).
- **deck-core lives arbosano-local** at `src/lib/deck-core/`. Framework-free, MST-free. It extracts to `@marlinjai/deck-core` at Phase C, not now.
- **Token types AND the arbosano token values are authored locally** in `src/lib/deck-core/brand/` for Phase A. Do NOT reach into lumitra-studio or create `brands/arbosano/brand.json` yet. Author them to the SAME schema (parent plan section 2.5) so the Phase C lift is a move, not a rewrite.

## Scope: the tasks

### T1. deck-core scaffold
`src/lib/deck-core/` with: `model/` (Zod schemas + inferred types for `DeckSnapshot`, `Slide`, `LayoutContainer`, `Block`), `render/` (the emitter), `brand/` (token types + arbosano values + `themeToTokensCss`), `index.ts` barrel. No mobx, no React.

### T2. Port `engine.css`
Extract the brand-agnostic override engine from the SHIPPED `public/deck/theme.css` into `src/lib/deck-core/render/engine.css`: the load-order rule, the specificity ladder with the two surgical `!important`s, the `center:false` centering-defeat CSS, the `.slide-frame` 3-row grid, the asymmetric `.split.s-*` helpers, `.stack`/`.fill`/`.center-v`. Move the arbosano pitch-specific component CSS (`.numbered`, `.ruled`, `.sitemap`, `.competitors`, `.q-pair`, `.pill`, per-`#id` hacks) into `render/patterns.css` (opt-in). Keep the Kolloquium custom-fragment keyframes available verbatim for the `CustomHTML` escape hatch.

### T3. `renderDeck(snapshot, tokensCss): string`
The tree walker. One `<section class="<surface>">` per slide, each wrapping one `.slide-frame`. Recurse `LayoutContainer` (frame/split/stack/grid/free) emitting the matching engine.css classes; dispatch `Block.type` to per-type HTML fragments (Heading/Text/List/Image/Video/Code/Badge/Table to start; EChart/Rive/Spline/CustomHTML can be stubbed-but-typed in Phase A). Wire `data-fragment-index` from `Block.fragment`. Emit `<head>` in this exact order: reset, reveal, fonts, tokens.css, engine.css, patterns.css. Emit the inlined `Reveal.initialize({...})` matching the shipped deck (1440x900, `center:false`, `transition:'fade'`, no plugins). Use `Reveal.on()` not `addEventListener`.

### T4. Brand tokens v1 (token half only)
In `src/lib/deck-core/brand/types.ts` define `LumitraColorValue` (with `hex`), `LumitraDimension`, `LumitraToken`, `LumitraTypographyValue`, `LumitraTokenSet` (primitives/semantics/components), `LumitraSemanticRole` (the frozen contract names). In `src/lib/deck-core/brand/arbosano.ts` author the arbosano token set seeded from the skill's exact `--c-*` values (forest/moss/bark/bone/paper/ink ramps, Fraunces/Inter/JetBrains Mono with the SOFT/WONK axes, `--tracking-*`). Implement `themeToTokensCss(resolved): string` that emits the frozen `--c-*` / `--surface-*` / `--font-*` / `--tracking-*` `:root` block byte-compatibly with the shipped `theme.css`. Single mode (`light`), single brand (`arbosano`), no world selection. Do NOT add `styleWorlds`, `core`, character, photo, motion, or the prompt emitter.

### T5. `pnpm deck` CLI
`src/cli/deck.ts`, copying the arg-parse shape from lumitra-studio's `generate.ts`. Input: a deck JSON path. Output: rendered reveal.js HTML to a target dir. deck-core is pure rendering with NO secrets, so the CLI needs NO Infisical wrapper (unlike the lumitra-studio script you are copying the shape from). Add a `deck` script to `package.json` (e.g. `node --experimental-strip-types src/cli/deck.ts`).

### T6. Acceptance (see Definition of done)

## The data model to implement

```
DeckSnapshot                       // plain JSON, Zod-validated, MST-free
  meta: { title, brandSlug, mode:'light', styleWorldId?, fidelityTier, reveal:{ width:1440, height:900, transition:'fade', ... } }
  slides: Slide[]
    Slide: { id, surface:'bone'|'forest', notes?, layout: LayoutContainer }

LayoutContainer: { kind, props, children:(LayoutContainer|Block)[] }
  kind: 'frame' | 'split'(ratio '7-5'|'5-7'|'8-4'|'4-8'|'9-3') | 'stack'(gap) | 'grid'(cols/rows/gap) | 'free'

Block: { id, type, props(frozen), children?, fragment?:{index,anim}, position? /* only under free */ }
  type: Heading|Text|List|Image|Video|Code|Badge|Table | EChart|Rive|Spline | CustomHTML
```

Hybrid layout: structured flex/grid containers for on-brand layouts (`.split`/`.stack`/`.slide-frame`), with `kind:'free'` the only place `position` is honored. Blocks carry no `position` unless their parent is `free`, so diffs stay clean.

## Definition of done

- `renderDeck(snapshotOfShippedDeck, themeToTokensCss(arbosanoTokens))` reproduces `public/deck/index.html`. DEFINE and DOCUMENT a whitespace/formatting normalization policy in a comment or short MD note: exact-byte is ideal; semantic-DOM-equal is acceptable if you document it and assert it in a test.
- `themeToTokensCss(arbosanoTokens)` output diffs cleanly against the shipped `theme.css` `:root` block.
- A byte/DOM-repro test and a token-emit test, both green, wired so `pnpm test` runs them (append to the existing `test` script in package.json in its existing style: `node --import ./scripts/tools-loader.mjs --experimental-strip-types <file>.mts`, or a dedicated test file in the same runner shape).
- `pnpm deck <sample.json>` renders a small hand-authored sample deck to working HTML. Include the sample JSON in the branch.
- `pnpm test` passes, `pnpm build` (next build) passes, `pnpm lint` (eslint --max-warnings=0) passes. NOTE on build: this worktree carries the merged Phase 4 better-auth + `pg` (Postgres) stack. `next build` is intentionally NOT Infisical-wrapped and is expected to build without secrets. If `pnpm build` fails specifically in the better-auth / `pg` / `DATABASE_URL` layer (a pre-existing env condition, NOT caused by your deck-core changes), do not chase it: record it as an open thread and treat your real deck-core gate as `pnpm test` (the new deck tests) + `tsc --noEmit` clean on `src/lib/deck-core/**` and `src/cli/deck.ts` + `pnpm lint`. Your changes are pure TS/CSS and must not introduce any new build error of their own.
- Produce the rendered output (the reproduced `index.html`) into a committed or easily-regenerated location so the operator can serve and screenshot-verify it. NOTE: screenshot verification is performed by the OPERATOR after your run (the headless Worker has no browser MCP). Do NOT block on browser tooling. Your job is the deterministic byte/DOM-equality test plus a runnable render. State in your final message the exact command to regenerate the rendered HTML.
- Single commit on this branch with a conventional-commit message describing the WHY. Keep `plans/2026-05-31-deck-core-phase-a-kickoff.md` in the branch (do not delete it, do not change its `status`; the operator flips it at merge).

## Gotchas (load-bearing, from the spec)

- **Build from the SHIPPED deck, not the SKILL recipe.** They diverge: shipped is 1440x900 (recipe says 1280x720), `.forest` (recipe says `.dark`), inlined init with no plugins (recipe says `deck.js` + RevealNotes), class selectors `.h1`/`.h2`/`.display` (recipe uses tag selectors), and the shipped deck has NO grain (recipe mandates it). Shipped wins.
- **Never override `display` on `.reveal .slides > section`.** Reveal owns it for active-slide gating. All layout lives on the inner `.slide-frame`.
- **Centering defeat needs BOTH halves**: `center:false` in init AND `text-align:left !important` in CSS. Omit either and it reverts to centered Times.
- The only two `!important`s that belong: `text-transform:none` and `text-shadow:none` (beating reveal's aggressive defaults), plus the `text-align:left`.
- **Pin reveal.js 5.x; use `Reveal.on()`**, not the deprecated `addEventListener`.
- **No em-dashes or en-dashes anywhere** (deck content, code, comments, commit messages). Use colons, parentheses, commas, periods.
- Secrets via Infisical only; never a literal in a script (not that deck-core needs any).
- The shipped deck carries dead/scratch code (`runDemo`, an `adjustViewportFit`, a `code:contains()` selector that throws). Do NOT reproduce it in the emitter.

## Out of scope (Phase A, do NOT build)

- The `/admin` deck zone, `createDeckTools`, the agent loop, live iframe, publish-to-PR (Phase B).
- `styleWorlds`, `core`, character rigs, photo/motion art-direction, the `themeToPromptContext` generative emitter (later).
- `themeToTailwindTheme` and dark mode (Phase B).
- Touching lumitra-studio: no `BrandConfig` edit, no `brands/arbosano/brand.json`, no `@marlinjai/deck-core` extraction (Phase C).
- The Vite WYSIWYG editor, MST, contentEditable (Phase D).

## Constraints

- Stay in this worktree. Do not modify files outside it. Reading absolute paths listed in "Read first" is fine; writing outside the worktree is not.
- Do not push to any remote. Do not open a PR. The operator handles push, PR, and merge after an adversarial review.
- Do not run destructive commands.
- When done, output a final message stating: what was built, the normalization policy you chose, the exact command to regenerate the rendered HTML for screenshot verification, and any open threads.
