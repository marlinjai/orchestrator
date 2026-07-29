---
task: drain-lib-extraction
verify: bats tests/drain_lib.bats tests/claude_marlin_extras.bats
# Target repo (--project): ~/software-dev/marlinjai-bootstrap
# Wave 1 / leaf L1. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 1: "Extract drain-lib.sh")
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L1)
shared_state: [drain, hooks]
---

# Goal

Factor the proven capture-drain machinery in `marlinjai-bootstrap` into a single reusable
shell library, `drain-lib.sh`, so every future drain (release-as-PR, discovery feeder) is a
~20-line caller instead of a copy of `capture-drain.sh`. Prove the library by refactoring the
existing `capture-drain.sh` to consume it (behaviour byte-for-byte unchanged), and generalize
the recursion guard to a SINGLE drain-agnostic sentinel so the SessionStart/SessionEnd hooks
do not grow an ever-longer `CAPTURE_HEADLESS || RELEASE_HEADLESS || ...` OR-chain as new drains
land. This is the cheap glue the rest of Wave 1/3 (L5 discovery feeder, L6 release drain) sits on.

## Read first

- `modules/claude-marlin-extras/scripts/capture-drain.sh` (the only drain today, 146 lines: the
  source of every pattern to factor).
- `modules/claude-marlin-extras/hooks/on-session-start.sh` (recursion guard at ~:34, fire-and-forget
  detach at ~:54-59) and `hooks/on-session-stop.sh` (recursion guard at ~:50, enqueue path).
- `modules/claude-marlin-extras/launchd/com.marlinjai.capture-drain.plist` (the timer that runs the drain).
- `tests/claude_marlin_extras.bats` (the existing BATS harness and its style: the new lib tests live here or in a sibling `.bats`).

## Scope

1. **`modules/claude-marlin-extras/lib/drain-lib.sh`** (new): a sourceable library exposing the
   patterns currently duplicated in `capture-drain.sh`. At minimum:
   - `drain_init <drain_name>`: set `DRAIN_NAME`, resolve `DRAIN_LOG`/`CLAUDE_BIN`/`PATH` defaults, define the `TS()` timestamp helper.
   - `drain_acquire_lock <prefix>` / `drain_release_lock`: the atomic `mkdir` lock + 30-min stale-lock eviction, with the `trap ... EXIT` release.
   - `drain_log <message>`: append `"$(TS) <message>"` to `DRAIN_LOG`.
   - `drain_debounce_entry <file> <age_secs>`: skip an entry younger than the threshold (return non-zero to `continue`).
   - `drain_spawn_headless <args...>`: run the headless `claude` invocation with the standard flags, ALWAYS setting the canonical headless sentinel (see point 3) so it can never re-trigger a hook.
   Keep names and semantics derived from what `capture-drain.sh` actually does; do not invent capability the current script lacks.
2. **Refactor `capture-drain.sh` to source and use `drain-lib.sh`.** The observable behaviour
   (queue draining, debounce, substantiveness filter, lock, `/sweep` + `/roadmap` render) MUST be
   unchanged. This refactor is the library's proof-of-use, not a behaviour change.
3. **Generalize the recursion guard.** Introduce ONE canonical drain sentinel env var (e.g.
   `CLAUDE_DRAIN_HEADLESS=1`) that `drain_spawn_headless` always sets, and make the SessionStart and
   SessionEnd hooks guard on THAT single var (keep honoring the legacy `CAPTURE_HEADLESS=1` for one
   release so nothing in flight breaks, but the new sentinel is the one future drains set). The point:
   adding L5/L6 must require ZERO further edits to the hooks. Document the sentinel contract at the top of `drain-lib.sh`.
4. **BATS tests** in a NEW file `tests/drain_lib.bats` (so the gate is scoped to this leaf, not the
   whole installer suite) covering the library in isolation: lock acquire/release + stale-lock
   eviction, debounce skip vs pass, `drain_log` output shape, and that `drain_spawn_headless` sets the
   sentinel (mock `CLAUDE_BIN` to a tracing stub; never spawn a real `claude`). Plus a smoke test that
   the refactored `capture-drain.sh` still sources cleanly and runs a no-op dry pass. Follow the style
   of `tests/claude_marlin_extras.bats` and reuse `tests/helpers.bash` if present.

## Definition of done

- `lib/drain-lib.sh` exists, is `shellcheck`-clean if shellcheck is in the repo's tooling, and exposes the functions above.
- `capture-drain.sh` is refactored onto the library with no behaviour change (the existing capture tests, if any, still pass; the new smoke test passes).
- The hooks guard on the single canonical sentinel; a comment in each hook explains why there is no per-drain OR-chain.
- New BATS tests pass: `bats tests/drain_lib.bats tests/claude_marlin_extras.bats` is green (the leaf-scoped gate).
- A one-paragraph note added to `marlinjai-bootstrap`'s relevant module README (or the drain section of its docs) showing the ~20-line caller skeleton, so L5/L6 authors copy the right shape.
- Single conventional commit on the branch describing the WHY (cheap glue for future drains).

## Constraints

- Stay in this worktree; do not push. No behaviour change to the capture drain.
- Do not delete the legacy `CAPTURE_HEADLESS` honoring in the same commit that introduces the new sentinel (leave a clean one-release migration path, then a follow-up `open_thread` to remove it).
- No em-dashes / en-dashes anywhere (this repo's style + global style).
- bash, not a rewrite into another language. Keep it POSIX-ish / bash as the existing scripts are.

## Notes

- The roadmap's Wave-0 "Recursion guard" line ("OR every `*_HEADLESS` flag into the capture hook
  BEFORE a second headless drain exists") is satisfied MORE cleanly by the single-sentinel approach
  here than by an OR-chain: encode that reasoning in the commit message.
- File an `open_thread` for the eventual removal of the legacy `CAPTURE_HEADLESS` alias.
