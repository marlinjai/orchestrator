---
task: doc-reconciler-scaffolding
spec: src/closed_loop_sync/reconcile.py
verify: uv run --extra dev pytest -q
verify_fix_cap: 3
verify_timeout_s: 1200
---

# Goal

Implement the DETERMINISTIC shell of the doc-reconciler in `src/closed_loop_sync/reconcile.py` of the `closed-loop-sync` package: `classify_plans()` plus the supporting data structures and an `apply()` that writes proposed edits. The "is feature X actually shipped" judgment stays OUT of this module, delegated through an injected `judge` callable so the logic is pure and unit-testable. The contract is the module docstring in `reconcile.py`. Read it first, it is authoritative.

## Read first

- `src/closed_loop_sync/reconcile.py` (the CONTRACT docstring + the `classify_plans` stub)
- `src/closed_loop_sync/roadmap.py` (the already-implemented sibling: reuse its frontmatter-parsing / plan-detection helpers and style, do NOT duplicate them; refactor shared helpers into a small internal module if cleaner, keeping roadmap.py's public behavior and tests green)
- `tests/test_roadmap.py` and `tests/test_baseline.py` (the suites that must stay green)
- The document-lifecycle status vocabulary: terminal = `completed`/`archived`/`rejected`; lifecycle = draft, decided, in-progress, completed, archived, rejected.

## Definition of done

- A clear input model (dataclasses or typed dicts) for: a parsed plan record, a shipped-signal record (e.g. a feature/path/commit hint that something is implemented), and a proposed reconciliation action.
- `classify_plans(plans, shipped_signals, judge=None)` implemented deterministically:
  - `shipped-but-stale-status` (judge says shipped, plan status is non-terminal) -> propose a status bump to `completed`
  - `shipped-but-no-plan` (a shipped signal with no matching plan) -> propose a new plan (status: completed) + a README-note action
  - `genuinely in-flight` (judge says not shipped, status forward) -> leave, or propose `in-progress` where appropriate
  - `claims-done-but-not-done` (status `completed` but judge says not shipped) -> FLAG ONLY, never auto-close (this is the rare case; conservatism is required)
  - `judge=None` defaults to a conservative verdict (treat as not-shipped / leave), so the function is fully testable with no LLM
- An `apply(actions, dry_run=False)` (or equivalent) that materializes the safe, deterministic edits (status-field rewrites in frontmatter; new-plan stub creation) and returns a summary. Status edits must rewrite ONLY the `status:` frontmatter value, preserving the rest of the file byte-for-byte.
- Hermetic pytest coverage in `tests/` (temp-dir fixtures, a FAKE judge): every classification branch, the conservative `judge=None` default, the FLAG-not-close guarantee for claims-done-but-not-done, and that `apply()` rewrites only the status line.
- `uv run --extra dev pytest -q` passes (all existing tests stay green).
- NO em-dashes or en-dashes in any generated content (new-plan stubs, README notes). Hard rule.
- Single conventional-commit on this branch.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do NOT add real git invocation or any LLM/network call: shipped-signals and the judge are INPUTS/injected. Wiring real git + a real agent judge is a later integration step, explicitly out of scope.
- Do NOT change the `roadmap render` CLI behavior or break its tests. If you extract shared helpers, keep roadmap.py's public API and all its tests passing.
- Keep `cli.py`'s `reconcile` subcommand contract compatible (it may stay "not implemented" at the CLI level if full wiring is out of scope, but `classify_plans`/`apply` must be importable and complete).
- Do not push to any remote. When done, output a final completion message.

## Notes

- If a contract point is ambiguous, pick the most useful deterministic interpretation, document it in the docstring, and pin it with a test rather than escalating.
- Bias the design toward the real-world failure mode (build-ahead-of-docs): be thorough on the shipped-but-stale-status and shipped-but-no-plan paths, conservative on auto-closing.
