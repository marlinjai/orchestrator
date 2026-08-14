---
task: lumitra-studio-p0-design-audit
spec: docs/plans/2026-08-14-design-rethink.md
shared_state: [workspace]
verify: test -f docs/audits/2026-08-15-p0-design-audit.md && grep -q "## Token and spacing spec" docs/audits/2026-08-15-p0-design-audit.md
verify_fix_cap: 1
verify_timeout_s: 900
---

# Goal

Execute Phase P0 of the design-rethink plan (`docs/plans/2026-08-14-design-rethink.md`, table row P0: "Design audit sweep with screenshots per surface, produce annotated findings + the token/spacing spec", risk: none, read-only). This is a RESEARCH deliverable, not a code change: no application files should be touched. Use the `ui-ux-design-audit` skill.

## Read first

- `docs/plans/2026-08-14-design-rethink.md` in full (the whole plan, not just the P0 row: the structural argument about eight noun-surfaces vs three acts matters for what the audit should be looking for)
- The live app at studio.lumitra.co (read-only, screenshot each top-level surface: Home, Chat, Characters, Products, Locations, Campaigns, Workflows, Assets)
- `src/app/globals.css` or wherever the design tokens live (the three color-axis system, Geist Mono for machine values), so the audit's token/spacing spec section is grounded in what actually exists, not invented

## Definition of done

Write `docs/audits/2026-08-15-p0-design-audit.md` containing:
1. A screenshot (or clear description if screenshot tooling isn't available in this environment) of every top-level surface
2. Annotated findings per surface: what's inconsistent, what breaks the "three acts" argument from the plan, concrete UI/UX issues (use the `ui-ux-design-audit` skill's framework, not an ad hoc list)
3. A `## Token and spacing spec` section: the actual current token values (colors, spacing scale, radius, font sizes) extracted from the codebase, plus recommended additions/fixes if gaps are found, not a redesign, an honest inventory plus gap list
4. This is read-only research. Do NOT propose or make code changes. Do NOT touch any file except the new audit doc.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- The only file this task creates or modifies is `docs/audits/2026-08-15-p0-design-audit.md`.
- No screenshots of authenticated/private data if the audit requires signing in, use placeholder/empty-state views or describe the surface structurally instead.

## Notes

This is explicitly the LOW-RISK, reversible half of the redesign work per the consolidation plan (`docs/plans/2026-08-15-studio-consolidation-and-redesign-sequencing.md`). P1 (the nav shell implementation) is a separate, NOT-yet-dispatched task that should be scoped from THIS audit's findings, not run in parallel with it blind. Do not attempt P1 in this task.
