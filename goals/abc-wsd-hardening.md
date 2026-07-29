---
task: abc-wsd-hardening
verify: pnpm typecheck && pnpm test -- --run
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Harden the WS-D dashboard per-variant heatmap feature that just merged (PR #22). Two things: (1) tighten test coverage of the variant-heatmap data flow and edge cases, and (2) fix the one UX dead-end the reviewer flagged: following the experiments-page heatmap link lands the user with the experiment arm pre-selected in the VariantPicker but with NO page URL chosen, so nothing renders until they also pick a URL, which can read as a dead-end.

## Read first

- `packages/dashboard/src/app/(dashboard)/heatmap/page.tsx` (reads `experiment_id`/`variant`; `selectedUrl` starts empty with no auto-select).
- `packages/dashboard/src/components/heatmap/VariantPicker.tsx` and `VariantHeatmapCompare.tsx`.
- `packages/dashboard/src/lib/{heatmap-experiments.ts, queries/heatmap.ts}` and the API route `packages/dashboard/src/app/api/heatmap/by-selector/route.ts`.
- `packages/dashboard/src/app/(dashboard)/experiments/[experimentId]/page.tsx` (the heatmap link that carries `experiment_id`+`variant` but no url).
- Existing WS-D tests: `packages/dashboard/src/__tests__/{heatmap-experiments-loader,heatmap-query-builder,heatmap-variant-routes}.test.ts`.

## What to change

1. UX next-step fix: when the user arrives with an `experiment_id`/`variant` but no `url`, make the next step obvious and non-dead-end. Preferred: if the project has exactly one tracked URL for that experiment, auto-select it; otherwise show a clear "pick a page to see this variant's heatmap" prompt listing the tracked URLs. Keep it consistent with the existing dashboard UI conventions. Do not change query/API signatures.
2. Tests: add coverage that the page/loader threads `experiment_id`+`variant` into the query functions and that the by-variant MV path is selected; the unknown/stale-variant empty state renders; the new auto-select / prompt behavior works (single-url auto-select vs multi-url prompt).

## Definition of done

- The `verify` gate passes (typecheck + full test run).
- `git push -u origin orchestrator/abc-wsd-hardening` then open a PR: `gh pr create --base main --title "feat(dashboard): WS-D hardening (variant-heatmap tests + pick-a-URL UX)" --body "<what/why/how-verified>"`. NO em-dashes/en-dashes. End the PR body with a blank line then: 🤖 Generated with [Claude Code](https://claude.com/claude-code)
- Few conventional commits describing the why.

## Constraints (hard, unattended overnight run)

- This is polish on an already-merged, working feature. Do NOT redesign the heatmap rendering or change the query/API/MV layer. Scope strictly to the UX next-step + tests.
- NEVER merge to main. NEVER push to main. Only push your `orchestrator/abc-wsd-hardening` branch and open a PR.
- Do NOT apply migrations, touch infra, or make live secret-backed calls. Visual/pixel correctness and live-ClickHouse data correctness still need a human; do NOT attempt to verify against a live database. If a change seems to need any of these, ESCALATE.
- Stay in this worktree.

## Notes

Pixels are not auto-verifiable here; your job is the logic + UX-flow fix + tests. Note in the PR body what still needs human visual QA (the side-by-side grid responsiveness, the live by-variant data check).
