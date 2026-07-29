---
task: lola-ft-phase2-sides
spec: docs/plans/2026-06-21-family-tree-completeness-design.md
verify: pnpm --filter @lola/web typecheck && pnpm --filter @lola/web test && pnpm --filter @lola/web i18n:check
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Phase 2 of family tree completeness: show maternal/paternal SIDE in the visual tree. Today all grandparents render in one undifferentiated "GRANDPARENTS" band, so a viewer cannot tell which grandparents belong to which parent. Group the grandparent band into two labeled clusters ("Mamas Seite" / "Papas Seite"), derived purely from the existing graph, with a graceful fallback to a single band when side cannot be determined.

This is frontend-only. The design + locked decisions are in `docs/plans/2026-06-21-family-tree-completeness-design.md` (read it first).

## Read first

- `docs/plans/2026-06-21-family-tree-completeness-design.md` (the design; decisions are locked there)
- `apps/web/src/components/family-tree/compute-tree-layout.ts` (the layout engine: `parentsByChild`, `coupleMap`, `isGrandparentReachableThroughParent`, and the ancestor-sort block that already computes `ancestorToChildIdx`)
- `apps/web/src/components/family-tree/generation-row.tsx` (renders a band's items)
- `apps/web/src/components/family-tree/types.ts` (`LayoutPerson`, `GenerationData`, `GenerationItem`)
- `apps/web/src/components/family-tree/relationship-display.ts` (the single display source from Phase 1; reuse it, do not duplicate label/color logic)
- `apps/web/src/components/family-tree/person-circle.tsx` (how a node renders)

## What to build

1. **Derive side in `compute-tree-layout.ts`.** The focal child's two parents are `person1` / `person2` of the parents couple (see `parentsByChild` + `coupleMap`). A grandparent connects to a parent via a `relativeConnections` entry of `connectionType === 'PARENT_CHILD'` (grandparent -> parent). For each grandparent-generation node (generation rank 0), determine which parent it is an ancestor of, and tag it with a stable side key (e.g. parent's id) plus that parent's `firstName` and `gender`. The existing `ancestorToChildIdx` / `isGrandparentReachableThroughParent` logic already walks these edges: reuse it, do not invent a second traversal.
2. **Render two labeled clusters** for the grandparent band in `generation-row.tsx` (or a small dedicated sub-component): grandparents whose side is parent1 in one cluster, parent2 in the other, each under a small label. Keep the visual language consistent with the existing band labels (the uppercase muted caption style).
3. **Cluster label rule:** if the side-parent's `gender` is `FEMALE` -> "Mamas Seite"; `MALE` -> "Papas Seite"; unknown -> "{parentFirstName}s Seite". Add the i18n keys under a new `familyTree.sides` namespace in BOTH `apps/web/messages/de.json` and `apps/web/messages/en.json` (de: motherSide "Mamas Seite", fatherSide "Papas Seite", parentSide "{name}s Seite"; en: "Mum's side", "Dad's side", "{name}'s side"). German non-ASCII must be \uXXXX-escaped to match the file convention; run `pnpm --filter @lola/web exec prettier --write` on the two message files after editing.
4. **Graceful fallback (required):** when side cannot be derived for the band, fall back to today's single flat row. Specifically fall back when: there are fewer than 2 parents; the two parents are same-gender (so "Mama/Papa" is ambiguous, use "{name}s Seite" per parent instead, never two identical labels); a grandparent maps to neither parent (place it in a neutral/unsorted group, never drop it); or there are zero side-taggable grandparents. NEVER render an empty cluster and NEVER drop a person from the tree.
5. Apply the same side grouping to aunts/uncles IF it falls out cheaply from the same derivation; if it expands scope or risks the parents-band layout, leave aunts/uncles as-is and add an `open_thread` note. Side grouping of the GRANDPARENT band is the must-have.

## Definition of done

- Grandparents visually grouped into two labeled side clusters, with the fallbacks above.
- New unit test (node:test, co-located `*.test.ts`, added to the `test` script list in `apps/web/package.json` which is an explicit file list, NOT a glob) for the side-derivation function: covers two-parent split, single-parent fallback, same-gender parents, and an unmappable grandparent (must not be dropped).
- `pnpm --filter @lola/web typecheck` green
- `pnpm --filter @lola/web test` green
- `pnpm --filter @lola/web i18n:check` green (de and en key parity)
- Flowmap: after your changes, run `pnpm turbo build --filter=@lola/web && pnpm --filter @lola/web flowmap:gen && pnpm --filter @lola/web flowmap:check`; if any `apps/web/public/flowmap*.json` changed, commit them. (Line shifts in tracked files can drift the board; this is expected and must be committed.)
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Frontend-only. Do NOT change the backend relationship engine, the `legacy-kind-mapper`, the DB schema, or any API contract. Side is DERIVED in the web layout, no new DB field (this is locked in the design doc).
- Reuse `relationship-display.ts` for any label/color needs; do not add a second source of relationship display truth.
- Stay in this worktree. Do not push to any remote. Do not run migrations or touch any database. Do not deploy.
- Locked decisions still hold: in-law distinction is display-only; gendered labels need `Person.gender`; label refinement stays frontend-only.
- If a genuine product/scope question arises (e.g. how to label sides for same-gender parents beyond the rule above, or whether to restructure the parents band), escalate rather than guessing.
- When done, output a final message that the task is complete.
