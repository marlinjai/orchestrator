---
task: studio-canvas-autosave
shared_state: [authoring]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Make the node canvas not lose work. Today saving is manual (the Save button), the "Saved / Unsaved" chip can lie after navigation, and edits to an already-saved workflow can be lost if you navigate away or close the tab without clicking Save. Add debounced autosave for an already-saved workflow plus a navigation flush, and make the save-state chip truthful. This is a behavior/UX fix, no visual-render judgment needed.

## Read first

- `src/components/workflows/EditableWorkflowCanvas.tsx` (the authoring shell: `onSave`, `dirtyCount`, the Save / UNSAVED chip framing near the header, hydration from `initial`, the canvas state the layout is built from)
- `src/lib/workflow/canvas-layout.ts` (`canvasToLayout`: how the live canvas is snapshotted to the persistable layout)
- `src/lib/workflow/saved-store.ts` + `src/app/api/v1/workflows/[savedId]/route.ts` (how a saved workflow is updated; the holder-row save path the manual Save already uses)
- `src/lib/canvas/dirty.ts` (`computeDirty` / `dirtyCount`: the dirty signal autosave triggers on)
- The save endpoint the manual Save button already calls (find it from `onSave`), so autosave reuses the SAME endpoint and payload, never a new contract.

## Definition of done

1. **Debounced autosave (already-saved workflows only).** When the canvas is dirty AND the workflow already has a `savedId`, debounce ~2s of inactivity then PATCH the saved workflow's `canvasLayout` (+ definition) via the EXISTING save endpoint/payload the manual Save uses. A brand-new, never-saved canvas does NOT autosave (no save target): it shows "Unsaved" and relies on manual Save to create the holder first. Autosave coalesces (a new edit during a pending save resets the debounce; never fire two concurrent saves for the same workflow).
2. **Navigation flush.** On `visibilitychange` -> hidden and on `beforeunload`, if there is unsaved dirty state for a saved workflow, flush it: a `fetch(..., { keepalive: true })` (or `navigator.sendBeacon` with an `application/json` Blob) to the same save endpoint, so the session cookie rides along and the dual-gate auth still applies. Best-effort; do not block navigation with a synchronous prompt.
3. **Truthful chip.** The header chip reflects real state: `Saving...` while a save (manual or auto) is in flight, `Saved` when clean and persisted, `Unsaved` when dirty (or never saved). No state where the chip says "Saved" while dirty edits are pending.
4. **No double-save / no regression of manual Save.** The manual Save button still works unchanged; autosave and manual Save share one save function and one in-flight guard.
5. **Tests:** autosave fires a save after the debounce when dirty + savedId present, and does NOT fire for a never-saved canvas; a new edit during a pending save coalesces (one save, latest state); the chip transitions dirty -> Saving -> Saved; the flush path posts to the save endpoint on hidden/unload (mock the endpoint + the timers). Use fake timers for the debounce, mirroring existing canvas test patterns.

## Constraints

- Reuse the EXISTING save endpoint + payload; do NOT add a new route or change the save contract. No Prisma migration.
- Autosave must respect the same auth as manual Save (it goes through the same gated endpoint; the session cookie is sent automatically same-origin).
- Keep it scoped to the editable canvas; do not touch the executor, the run path, or the read-only overlay.
- No em-dashes or en-dashes anywhere.
- Make a SINGLE conventional commit on this branch describing the WHY. Do NOT push or merge. When done, output a final message that the task is complete.
