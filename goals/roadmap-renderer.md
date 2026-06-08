---
task: roadmap-renderer
spec: src/closed_loop_sync/roadmap.py
verify: uv run --extra dev pytest -q
verify_fix_cap: 3
verify_timeout_s: 1200
---

# Goal

Implement the deterministic ROADMAP renderer in the `closed-loop-sync` package: `render_roadmap()` in `src/closed_loop_sync/roadmap.py`, already wired through `src/closed_loop_sync/cli.py` (`closed-loop-sync roadmap render`). It aggregates every non-terminal FUTURE plan across given repo roots into a ranked, derived ROADMAP markdown for the autonomous orchestrator to consume. The full contract is the module docstring in `roadmap.py`. Read it first, it is authoritative.

## Read first

- `src/closed_loop_sync/roadmap.py` (the CONTRACT docstring: inputs, selection, ranking, output)
- `src/closed_loop_sync/cli.py` (how render_roadmap is invoked; keep the CLI contract stable)
- `README.md` and `tests/test_baseline.py` (baseline that must stay green)
- The document-lifecycle status vocabulary: a plan is `type: plan` OR lives under a plans path (`/plans/`, `/specs/`, `/research/`, `/decisions/`); terminal statuses are `completed`, `archived`, `rejected`. Frontmatter is YAML between `---` fences; all fields optional with path-based fallback for missing `type`.

## Definition of done

- `render_roadmap(roots, include_in_progress=False)` is fully implemented per the module contract:
  - scans each root recursively for markdown plan docs, parses YAML frontmatter (use the `pyyaml` dep)
  - identifies plans by `type: plan` or plans-path inference
  - selects FORWARD work only: include `draft`/`decided`/non-terminal-not-started; exclude `completed`/`archived`/`rejected`; exclude `in-progress` unless `include_in_progress=True`
  - ranks deterministically: `leverage` (HIGH>MEDIUM>LOW, missing = lowest) then `date` (older first) then title
  - returns a markdown string with a DERIVED-PROJECTION warning header, ranked items, each tracing to its source plan path + status
  - NO em-dashes or en-dashes anywhere in the output (use colon, parentheses, comma, period). This is a hard repo + global rule.
- Comprehensive pytest coverage in `tests/` using temp-dir fixtures of sample plan files, covering at minimum: status filtering (each terminal status excluded, each forward status included), the `include_in_progress` toggle, leverage ranking order, missing-frontmatter path-inference fallback, stable ordering on ties, and that the output contains no em/en dash characters.
- `uv run --extra dev pytest -q` passes (the baseline two tests stay green).
- Single commit on this branch with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do NOT implement `reconcile.py` (a later Worker owns the doc-reconciler). Leave its stub untouched.
- Do NOT add network or LLM calls to `roadmap.py`: it must stay deterministic and pure (that is what makes it unit-testable). Any judgment-requiring logic is out of scope here.
- Keep the CLI command surface (`closed-loop-sync roadmap render --root ... -o ...`) backward-compatible with `cli.py`.
- Do not push to any remote. Do not run destructive commands.
- When done, output a final message that the task is complete.

## Notes

- The renderer will be run against real roots like `~/software-dev/knowledge-base/plans` and each repo's `docs/plans`, but your tests must NOT depend on those live dirs: use self-contained temp fixtures so the suite is hermetic.
- If you discover a genuinely ambiguous contract point, pick the most useful deterministic interpretation, document it in the function docstring, and add a test pinning it (rather than escalating on a minor judgment call).
- Add `uv.lock` if `uv` generates one; it is fine to commit.
