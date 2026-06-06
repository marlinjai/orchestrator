---
task: deck-core-phase-b
spec: plans/2026-06-01-deck-core-phase-b-kickoff.md
---

# Goal

Implement deck-core Phase B: the deck zone in arbosano's `/admin` agent loop, so the agent authors reveal.js decks live (chat -> edit a DeckSnapshot JSON -> render a static artifact -> live iframe -> publish PR), localhost-only. Your authoritative spec is `plans/2026-06-01-deck-core-phase-b-kickoff.md` in this worktree. READ IT IN FULL FIRST. This is one PR on branch `feat/deck-core-phase-b` (this worktree, off `main` which carries Phase A deck-core and Phase 2.5 EditScope).

This phase MODIFIES SECURITY-CRITICAL CODE (the four-fence agent toolset). The overriding rule: your changes are ADDITIVE. You extend the fences for decks; you do NOT refactor or weaken the existing fences. Every existing fence test must stay green.

## Read first (in order)

1. **Your spec**: `plans/2026-06-01-deck-core-phase-b-kickoff.md` (this worktree). Read every line: the load-bearing design decision (static artifact, NOT a runtime route), the tasks T1-T6, the integration-point signatures, and the gotchas.
2. **The four-fence toolset you extend**: `src/lib/admin/tools.ts` (full) + `src/lib/admin/__tests__/tools.fence.test.mts` + `src/lib/admin/__tests__/tools.editscope.test.mts`. Understand EditScope, buildAllowGlobs, assertWritablePath, the fence order, and violatesContentShape before changing anything.
3. **The zone policy**: `src/lib/zones.ts`.
4. **The agent loop + chat route**: `src/lib/admin/agent.ts` + `src/app/api/admin/chat/route.ts`.
5. **The session/runner + publish**: `src/lib/worktree-sessions/index.ts` + `runner.ts`, `src/app/api/admin/publish/route.ts`, `src/lib/admin/git-identity.ts`.
6. **The deck-core API you integrate**: `src/lib/deck-core/index.ts` + `src/cli/deck.ts` (mirror its parse -> brand-resolve -> render -> write sequence for the render_deck tool).

## Decided defaults (do NOT re-litigate)

- **Storage = DeckSnapshot JSON source + committed static HTML artifact.** Source at `src/content/decks/<id>.json`; artifact at `public/decks/<id>/index.html` (+ tokens.css, engine.css, patterns.css). A `render_deck` tool regenerates the artifact. NO runtime render route. The iframe serves the static artifact through the existing NextDevRunner unchanged. This honors the Phase A decided default "deck ships as a static asset, no build step at serve time."
- **Extend, do not fork.** Thread a `target: 'site' | 'deck'` parameter through createTools / the agent / the chat route. Do NOT copy tools.ts into a parallel file.
- **Additive security only.** Add a deck allow-set, a `fence1-deck-schema` validation fence, and skip the JSX content-shape check for deck JSON. Do NOT change the existing fence order, the existing globs, or the existing matchers. The dash-guard stays on all writes.
- **Localhost-only.** Hosted scope must NOT grant deck globs. Deck authoring is `target='deck'` under localhost scope only.

## Scope: the tasks (full detail in the spec)

- **T1** zone: append `src/content/decks/**` and `public/decks/**` to CONTENT_GLOBS in zones.ts. Do NOT add src/lib/deck-core/** to BLOCKED_GLOBS (shared library, agent-editable behind the reviewer gate). If you add any new deck-agent machinery, mirror it in BLOCKED_GLOBS AND AGENT_MACHINERY_GLOBS (they move in lockstep).
- **T2** `createDeckTools` via a `target` param: deck allow-set, the `fence1-deck-schema` fence using deck-core's parseDeckSnapshot, skip violatesContentShape for deck JSON (isDeckFile helper, POSIX-normalize the path), extend the ToolError.fence union, and a `render_deck` tool that mirrors src/cli/deck.ts (parseDeckSnapshot -> themeToTokensCss(arbosanoTokens) -> renderDeck -> write artifact, all writes through assertWritablePath).
- **T3** deck-flavored agent: refactor the SYSTEM_PROMPT const into a `createSystemPrompt(target)` factory; the deck variant teaches the DeckSnapshot model + 12 block types + 5 container kinds + fragments + the CustomHTML escape hatch + the no-em-dash rule + "call render_deck after editing". runAgent loop is domain-agnostic, reuse verbatim.
- **T4** thread `target` through chat/route.ts (default 'site', validate enum, 400 on bad input) and a lean `/admin` UI affordance to pick deck-vs-site.
- **T5** preview = the static artifact served by NextDevRunner (no new Runner); publish = reuse POST /api/admin/publish verbatim.
- **T6** a seed deck + its rendered artifact + tests.

## Definition of done

- `pnpm test` green, including NEW deck tests: (a) createDeckTools allows `src/content/decks/x.json` + `public/decks/**`, rejects out-of-zone; (b) the deck-schema fence rejects malformed DeckSnapshot with `fence1-deck-schema`; (c) the JSX content-shape fence does NOT fire on deck JSON; (d) `render_deck` output matches `renderDeck` (use normalizeHtml to compare). Wire the new test(s) into the `test` script in package.json in its existing style.
- THE EXISTING `tools.fence.test.mts` AND `tools.editscope.test.mts` MUST STAY GREEN. If you cannot extend the fences without regressing them, STOP and record an open thread rather than weakening a fence.
- `tsc --noEmit` clean, `pnpm lint` clean, `next build` green (same pre-existing better-auth/pg env caveat as Phase A: a bare-build failure in that layer is NOT your regression; your real gate is the tests + tsc + lint + your additive code introducing no new build error).
- A seed deck committed at `src/content/decks/` + its rendered artifact at `public/decks/`, proving the round-trip.
- NOTE: the LIVE INTEGRATION TEST (real agent on localhost authoring a deck, iframe render, publish PR) and the ADVERSARIAL FENCE REVIEW are performed by the OPERATOR after your run (the headless Worker has no ANTHROPIC-key live loop or browser). Do NOT block on them. Your job is the deterministic build + unit tests + the seed-deck round-trip. In your final message, state exactly how to drive the live loop (env vars, the deck-target request shape) and which files changed the fence behavior so the operator can adversarially review them.
- Single commit on `feat/deck-core-phase-b` with a conventional-commit message describing the WHY. Keep the two plan docs already in the worktree (the B handover, and the A handover now flipped to status: completed).

## Constraints

- Stay in this worktree. Reading absolute paths is fine; writing outside is not.
- Do not push to any remote. Do not open a PR. The operator handles push, PR, and merge after an adversarial fence review + a live-loop run.
- No em-dashes or en-dashes anywhere (code, comments, commit message, the deck system prompt). The dash-guard scans added lines.
- Secrets via Infisical only; never a literal in a script.
- When done, output a final message: what was built, which files changed fence behavior (for the adversarial review), the exact way to drive the live deck-authoring loop, and any open threads.
