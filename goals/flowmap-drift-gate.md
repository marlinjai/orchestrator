---
task: flowmap-drift-gate
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice B)
depends_on: [flowmap-thumbs-storage-brain]
---

# Goal

Implement Slice B of the flowmap-next handover: a `flowmap:check` CI drift gate that fails when the committed `apps/web/public/flowmap.json` is out of date relative to the source (a route or annotation changed without regenerating). Mirror the existing `i18n:check` gate exactly. This branches off main AFTER Slice A merged, so `flowmap.json` is already purely structural (no `preview.thumbnail`).

## Read first

- `apps/web/scripts/check-i18n-parity.mjs`: the reference shape. Mirror its structure, exit codes, and CI ergonomics.
- The `"i18n:check"` script in `apps/web/package.json`.
- `.github/workflows/ci.yml`: find the i18n:check step (gated on `needs.changes.outputs.web == 'true'`, runs on source, no build) and mirror that wiring.
- `apps/web/scripts/generate-flowmap.ts` (`flowmap:gen`): reuse its in-memory generate path so the check regenerates the same structural map.
- `apps/web/public/flowmap.json`: the committed artifact you diff against.

## Scope and changes

- New `apps/web/scripts/check-flowmap.ts` + a `"flowmap:check"` script in `apps/web/package.json`.
- The check regenerates the map IN MEMORY (reuse the generator's build path, glob mode, no `.next` manifest, so it runs on committed source exactly like `i18n:check`) and structural-diffs against `apps/web/public/flowmap.json`. FAIL on any difference.
- Normalize out volatile fields before diffing: `generatedAt` (and `preview.thumbnail` too, defensively, though Slice A already removed it: the check must not depend on Slice A having run, so strip thumbnail keys if any survive).
- Error message on failure must say: run `pnpm --filter @lola/web flowmap:gen` and commit.
- Wire a `Check flowmap drift` step into `.github/workflows/ci.yml`, gated on `web` changes, mirroring the i18n:check step (source-only, no build).

## Definition of done

- `pnpm --filter @lola/web flowmap:check` passes on a clean (regenerated) tree.
- Negative test (manual is fine): editing a route/annotation without regenerating makes `flowmap:check` fail; regenerating makes it pass. Describe this in the PR notes.
- Web typecheck clean if the script is TS-compiled in CI (mirror how i18n:check is run; if it runs via `tsx`/`ts-node`, match that).
- The CI step is correctly gated and green on a clean tree.
- Conventional-commit on this branch, subject lowercase after the colon, e.g. `feat(flowmap): add flowmap:check drift gate mirroring i18n:check`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- No em-dashes or en-dashes anywhere. Use colons, parentheses, commas, periods.
- Do not modify the generator's output format; only add the checker and CI wiring. If you must touch `generate-flowmap.ts` to expose the in-memory build path, keep the change minimal and behavior-preserving.

## Notes

- `pnpm install` the worktree first, then `pnpm --filter @lola/flowmap build` (the checker imports the package's compiled core/next).
- If `flowmap:gen` needs anything at runtime that the checker can't replicate (e.g. a `.next` manifest), match exactly how i18n:check avoids that (glob/source mode). The whole point is it runs on committed source with no build.
- If anything contradicts repo conventions, prefer the conventions and record it via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message that Slice B is complete, naming the new script, the package.json entry, and the ci.yml step.
