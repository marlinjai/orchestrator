---
task: lola-ft-phase3-no-external
spec: docs/plans/2026-06-21-family-tree-completeness-design.md
depends_on: [lola-ft-phase2-sides]
verify: pnpm --filter @lola/web typecheck && pnpm --filter @lola/web test && pnpm --filter @lola/web i18n:check
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Phase 3 of family tree completeness: make sure nobody falls off the tree, and let the user add the remaining relations. Today people typed `GODPARENT` / `FAMILY_FRIEND` / `OTHER` are excluded from the tree (`TREE_EXCLUDED_TYPES`) and shunted into a "Weitere Personen" side panel (`SOFT_RELATIVE_TYPES`). The user's rule: nobody should be invisible. Read `docs/plans/2026-06-21-family-tree-completeness-design.md` first.

## Scope (build these)

1. **Godparents & family friends into the tree.** Remove `GODPARENT` and `FAMILY_FRIEND` from the "Weitere Personen" exclusion so they render in the tree in a dedicated soft-relations zone (they already have a `soft` color group in `relationship-display.ts`). Give them a sensible band/placement (e.g. alongside the parents generation or a clearly-labeled soft zone). Keep using `relationship-display.ts` for labels and colors.
2. **Editor completeness in `contextual-actions.tsx` (the guided editor):**
   - Add "Großtante/Großonkel hinzufügen" (great-aunt/great-uncle) as an addable relation on a grandparent node. The display + ranks already exist from Phase 1 (`GREAT_AUNT` / `GREAT_UNCLE` are rank 0).
   - Make "Partner hinzufügen" available on every person node, not only where it is today. The `ADD_PARTNER` action + `partnerOfRelativeId` plumbing already exist; widen where it is offered.
   - Add the matching i18n action labels/descriptions in both locales (German non-ASCII \uXXXX-escaped; prettier the message files after).

## Out of scope / ESCALATE (do NOT build blindly)

- The deeper "design out external people at the source" change: making registration / invite / onboarding ALWAYS connect a new person into the graph so the logged-in account is its own connected node (no floating duplicate like the account "Marlin Pohl" vs the parent node "marlin"). This spans auth-adjacent flows and is a product decision. ESCALATE it with a concrete proposal rather than implementing it. Capture your proposed approach as an `open_thread` and in the escalation message.
- Any cleanup/deletion/mutation of existing `OTHER` rows in ANY database. NEVER run a migration or a data mutation against any environment. At most, write a migration FILE if clearly warranted and leave it unapplied, and flag it.
- If after removing godparents/family-friends from the panel the "Weitere Personen" panel would only ever hold unconnected `OTHER` people, do NOT silently delete those people from the UI (that hides them, the opposite of the goal). Keep `OTHER` people visible (panel or a clearly-labeled "not yet connected" affordance) and ESCALATE the connect/merge UX as a product decision.

## Definition of done

- Godparents / family friends render in the tree, not the side panel; no person disappears from the UI.
- Great-aunt/uncle addable on grandparents; partner addable on every node; new i18n labels present in both locales.
- New/updated unit tests for the changed pure logic (placement helper, contextual-actions availability). Add any new test file to the explicit `test` list in `apps/web/package.json`.
- `pnpm --filter @lola/web typecheck` / `test` / `i18n:check` all green.
- Flowmap: `pnpm turbo build --filter=@lola/web && pnpm --filter @lola/web flowmap:gen && pnpm --filter @lola/web flowmap:check`; commit any changed `apps/web/public/flowmap*.json`.
- Single commit, conventional-commit message describing the WHY. Escalated items recorded as `open_thread`.

## Constraints

- Prefer frontend changes. Backend changes only if strictly needed to surface an existing relation, and never to the `legacy-kind-mapper` output contract (it feeds the LLM story prompt + cast resolver) or the DB schema.
- Reuse `relationship-display.ts`; do not duplicate relationship display logic.
- Stay in this worktree. Do not push to any remote. Do not run migrations, touch any database, or deploy.
- Escalate genuine product/scope/auth decisions (see "Out of scope / ESCALATE"); do not guess.
- When done, output a final message that the task is complete.
