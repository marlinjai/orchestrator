---
task: lumitra-studio-director-ux
spec: docs/specs/2026-06-19-multimodal-canvas-ui.md
depends_on: [lumitra-studio-canvas-vision]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Phase 4: surface the LLM director in the canvas UI. The director routes already exist and work (`POST /api/director/improve-prompt`, `POST /api/director/shot-description`); no UI calls them yet. Add a small, tasteful "Improve prompt" affordance so a creator can one-click rewrite a node's prompt via the director. Keep it thin and self-evident; this is the seed of the chat-director surface, not the full thing.

## Read first

- Spec `docs/specs/2026-06-19-multimodal-canvas-ui.md` (Phase 4).
- `src/app/api/director/improve-prompt/route.ts` (request: `{ prompt, brandSlug?, mode?, modelId? }`; response: `{ improvedPrompt, model, costUsd? }`) and `src/app/api/director/shot-description/route.ts`.
- `src/components/workflows/EditableNodeCard.tsx`: the prompt textarea block (rendered when `taskNeedsPrompt(data.task)`), `patch({ prompt })`, the node context.
- The dark Tailwind studio style used across the node card + `ModelPicker`.

## Definition of done

1. **Improve-prompt affordance.** On the node card's prompt block (only when `taskNeedsPrompt(data.task)` and the prompt is non-empty), add a small "Improve" button (icon + label, matching the card's existing small-control style). Clicking it POSTs the current prompt to `/api/director/improve-prompt` (include the active `brandSlug` if the canvas has one in scope), shows an inline loading state, and on success replaces the textarea content via `patch({ prompt: improvedPrompt })` (marking the canvas unsaved as any prompt edit does). On error, surface a small inline message; never silently swallow.
2. **No dead-ends.** Disable the button while a request is in flight and when the prompt is empty. Handle the unhappy paths (network error, non-200, empty improvedPrompt) with a visible message.
3. **Scope discipline.** Do NOT build the full chat-director / shot-list panel in this slice. The shot-description route may be wired as a SECOND optional affordance only if it fits cleanly in the same small pattern; otherwise leave it for a later slice and note an `open_thread`. Prefer shipping the improve-prompt button well over half-building two features.
4. **Tests.** A component-level test that the Improve button renders when a prompt is present and is hidden/disabled when empty; a test that a successful improve response updates the node prompt (mock the fetch). Do not call the real LLM in tests.
5. Full `verify` gate green. Single conventional commit with the Co-Authored-By trailer.

## Constraints

- Stay in this worktree; do not push. TypeScript strict. No em-dashes/en-dashes. Dark Tailwind studio style; match the existing node-card controls.
- Do NOT touch the backbone or the director ROUTES (they are done); this is UI only.
- Keep the network call client-side from the node card (the route already guards `studio.generate`); do not add a new API route.

## Notes

- This is a taste-sensitive UI slice. If a real product/taste decision arises (e.g. should "Improve" auto-apply or show a diff/preview first?), prefer the simplest reversible default (apply directly, the prior prompt is preserved in the node's generation history) and record the alternative as an `open_thread` rather than guessing big.
