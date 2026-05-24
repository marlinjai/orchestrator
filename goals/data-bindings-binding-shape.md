---
task: framer-clone-binding-shape
wave: 1
spec: docs/specs/wave-1/data-bindings-binding-shape-on-component-model.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/data-bindings-binding-shape-on-component-model.md` in the framer-clone repo. Establish the canonical data-binding shape stored on every ComponentModel node — a frozen `BindingsRecord` with read-mode entries, MST actions (`setBinding`, `clearBinding`, `clearAllBindings`), views (`getBinding`, `hasBindings`), and exported types in `src/lib/bindings/types.ts`. Phase 1 only USES read-mode but the discriminated union must reserve `'write'` and `'two-way'` so persisted snapshots survive Phase 2.

## Read first

- `docs/specs/wave-1/data-bindings-binding-shape-on-component-model.md` (full spec, including Files and changes table, API surface, test plan, definition of done)
- `src/models/ComponentModel.ts` (current state — where the new field, actions, views land)
- Any existing snapshot tests on ComponentModel for the round-trip pattern.

## Definition of done (from spec)

- Code lands and typechecks (`pnpm build`)
- `pnpm test` passes including new `src/models/__tests__/ComponentModel.bindings.test.ts`
- Spec frontmatter status moved to `done` in the spec file AND the row in `docs/specs/STATUS.md`
- Single commit on this branch with a clear message

## Open questions in the spec

If the spec lists open questions, pick the most pragmatic answer for THIS spec only and document the choice in the commit message. Do NOT escalate. Only escalate if the codebase fundamentally contradicts the spec.

## Constraints

- Stay in the worktree at `~/software-dev/ERP-suite/projects/framer-clone-orch-binding-shape`. Do not modify files outside it.
- Pre-MVP rule: no backwards compatibility shim for existing snapshots; field is optional, default `{}`.
- Do not push to remote.
- When done and verified, output a final message that the task is complete.
