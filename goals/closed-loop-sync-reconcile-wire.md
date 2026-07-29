---
task: closed-loop-sync-reconcile-wire
verify: uv run --extra dev pytest -q && uv run --extra dev ruff check src tests
# Target repo (--project): ~/software-dev/closed-loop-sync
# Wave 1 / leaf L2. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 1: "Flip 2 dead seams")
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L2)
---

# Goal

Flip the dead `reconcile` seam in `closed-loop-sync` so the CLI actually runs the already-built,
already-tested reconcile engine instead of refusing. The engine (`classify_plans` + `load_plans` +
`apply`) is complete and pinned by 26 passing unit tests; the only dead part is the CLI command,
which raises `SystemExit("reconcile: not implemented yet")`. Wire it, with the LLM judge left as
`None` (the conservative, fully-tested default: leave forward/completed plans untouched, only propose
stubs for unmatched shipped signals). The git-log / shipped-signal feed and a real judge are LATER
leaves, explicitly out of scope here.

## Read first

- `src/closed_loop_sync/cli.py:56-58` (the `SystemExit("reconcile: not implemented yet")` stub and its dead `classify_plans` import).
- `src/closed_loop_sync/reconcile.py`: `load_plans` (~:215), `classify_plans(plans, shipped_signals, judge=None)` (~:263), `apply(actions, dry_run=..., readme_path=..., plans_dir=...)` (~:461), and the data models `PlanRecord`, `ShippedSignal`, `ReconcileAction`, `ApplyResult`.
- `tests/test_reconcile.py` (26 tests; note the `judge=None` cases at ~:217-239 that pin the conservative default).
- `src/closed_loop_sync/_common.py` for the plans-path markers (`plans/`, `specs/`, `research/`, `decisions/`) used to discover plan roots under a repo.
- `README.md` + `pyproject.toml` for the exact test/lint invocation.

## Scope

1. **Wire `cli.py` reconcile** to: discover plan roots under `args.repo` (reuse the existing
   path-marker logic in `_common.py`; do not hardcode a single `plans/` dir), `load_plans(roots)`,
   `classify_plans(plans, shipped_signals=[], judge=None)`, then `apply(actions, ...)` writing to the
   repo's plans dir + `README.md`. Empty `shipped_signals` is correct for this slice (the feed is a later leaf).
2. **Add a `--dry-run` flag** (default off) that runs the full classify but calls `apply(..., dry_run=True)`
   so an operator can preview proposed edits without writing. Print a concise summary (counts +
   target paths) on both dry and real runs.
3. **Surface the result**: exit 0 on success with a one-line summary (`applied=N skipped=M`), non-zero
   only on a real error (missing repo path, unreadable plans). Do NOT re-introduce a `SystemExit` stub.
4. **Remove the dead `# noqa: F401` import** now that `classify_plans` is actually used.

## Definition of done

- `closed-loop-sync reconcile <repo>` runs the engine end-to-end with `judge=None`; `--dry-run` previews without writing.
- No `SystemExit("...not implemented...")` remains; the dead `# noqa` import is gone.
- New CLI-level test(s) added: a `reconcile` invocation over a temp repo fixture asserts the conservative behaviour (forward/completed plans untouched, an unmatched shipped signal proposes a stub) and that `--dry-run` writes nothing. Reuse the fixtures/patterns already in `test_reconcile.py`.
- `uv run pytest -q` passes (the 26 engine tests + the new CLI tests); `uv run ruff check src tests` clean.
- README "usage" updated to show the now-working `reconcile` command + `--dry-run`.
- Single conventional commit describing the WHY (wire the tested engine; judge stays None).

## Constraints

- Stay in this worktree; do not push.
- Do NOT build the shipped-signal (git-log) feed or any LLM judge in this slice: `shipped_signals=[]`, `judge=None`. Keep the seam flip small.
- Do NOT change the engine's behaviour or its tests; only wire the CLI to it.
- No em-dashes / en-dashes. Conventional-commit message.

## Notes

- The repo's dev deps (`pytest`, `ruff`) are under `[project.optional-dependencies].dev`, so the gate uses `uv run --extra dev ...`. Layout is `src/closed_loop_sync` + `tests/`.
- closed-loop-sync has NO git remote: the terminal artifact is a single conventional commit on the `orchestrator/closed-loop-sync-reconcile-wire` branch in the worktree. There is no PR to open; the operator reviews + merges the branch locally (the MERGE gate still holds).
- File an `open_thread` noting the two deferred follow-ons: the shipped-signal git-log feed, and the optional LLM judge, both later leaves.
