---
task: arbosano-phase-2-5-1
spec: plans/2026-05-31-phase-2-5-execution-plan-to-live.md
marlin_proxy: shadow
---

# Goal

Implement arbosano **Phase 2.5 sub-phase 2.5.1 ONLY**: generalize the worktree-session
`SessionManager` so it can run MULTIPLE concurrent per-admin preview sessions safely. You
run inside a git worktree on branch `feat/phase-2-5-1` off `main` (which already has Phase 4
better-auth, Phase 5, and the 2.5.0 EditScope + secret-starved preview merged). Build to
green with tests. Do NOT push, open a PR, merge, or deploy. The operator reviews + runs the
live boot + opens the PR.

This is pure-code, host-independent. Do NOT build 2.5.2 (preview proxy), 2.5.3 (the
ADMIN_DEPLOYMENT auth gate), or 2.5.4 (deploy/lockdown). Do NOT wire the better-auth gate
into the routes (that is 2.5.3). Do NOT touch infra.

## Why this exists

Today the manager runs ONE preview: a single fixed port (`DEFAULT_PORT = 3100`) and, in
practice, a single `"default"` key. For a hosted, multi-user `/admin` (a trusted ~3-person
team), several editors may have a live preview at once. Three gaps to close:

1. **Fixed port** -> only one `next dev` can bind 3100. Needs a dynamic port per session.
2. **No concurrency cap** -> N editors could spawn N webpack servers (~1 to 3GB each) and OOM
   the box. Needs a cap derived from `runner.memoryCeilingMb` vs a host-RAM budget.
3. **No idle reaping** -> idle worktrees + dev servers pin ports, RAM, and disk forever.
   Needs to stop the dev server + remove the worktree after N minutes idle.

## The hard constraint (read twice)

**The localhost single-operator flow MUST stay behaviorally unchanged.** Today: open
`/admin`, one session provisions on a port, the iframe renders it, Publish opens a PR. After
2.5.1, that exact single-operator path must still work end-to-end with no visible change.
The generalization is additive: one session is just the N=1 case. If a change would alter
the single-operator experience, you have over-reached.

## Repo-state precondition + reuse (never recreate)

- Branch `feat/phase-2-5-1` in a worktree off `main`. Clean tree at start or escalate.
- `src/lib/worktree-sessions/index.ts`: the `SessionManager`. It already keys sessions in a
  `byKey` Map and has `acquire`/`get` + an `editScope()` accessor (from 2.5.0). This is the
  seam you generalize. KEEP the 2.5.0 behavior (the `scrubEnv` + `secretsScript` selection
  for hosted scope) intact.
- `src/lib/worktree-sessions/port.ts`: exposes `probeBindable(port)`. Build a dynamic-port
  ALLOCATOR on top of it (e.g. probe a bounded range like 3100..3199 and return the first
  bindable port; reserve it for the session). Do not bind-and-leak; the allocator must be
  race-safe enough for sequential acquires (the manager already coalesces in-flight acquires
  per key via its `inflight` Map).
- `src/lib/worktree-sessions/runner.ts`: `RunnerSpawnArgs` already carries `port`,
  `secretsScript`, `scrubEnv`; `memoryCeilingMb` (1024) is the per-session RAM promise. Use
  `memoryCeilingMb` for the concurrency cap. KEEP `--webpack` load-bearing (never Turbopack);
  keep the existing argv + env unit tests green.
- `src/lib/auth-session.ts`: `worktreeKeyForUser(...)` (Phase 4) is the key the routes WILL
  pass per-admin in 2.5.3. Do NOT wire it into the routes here. The manager must accept an
  arbitrary string key (it already does); the routes keep passing their current key until
  2.5.3. The point of 2.5.1 is the manager mechanism, not the route-layer identity.
- The admin API routes (`src/app/api/admin/*`) call the manager. Touch them ONLY if strictly
  necessary to pass a key/port through; do not change their auth or behavior.

## Build (2.5.1 only)

### Dynamic ports
- Each session acquires its own port via the allocator (not the fixed 3100). The session
  already records + returns its port; the iframe/preview uses `session.port` (unchanged
  contract). For the single localhost session, a probed port is fine (3100 if free); the
  operator experience is identical (the UI already reads the session's port).
- A released/reaped session frees its port for reuse.

### Concurrency cap
- A configurable cap on concurrent live sessions, defaulting to a value derived from
  `runner.memoryCeilingMb` vs a host-RAM budget (read total RAM via `os.totalmem()`, reserve
  headroom for the admin app + OS, then `floor(budget / memoryCeilingMb)`, clamped to >= 1).
- When at the cap, a new `acquire` for a NEW key does NOT spawn; it returns a clear, typed
  "at capacity" outcome (an error status the route can surface), never an unbounded spawn or
  a crash. Re-acquiring an EXISTING key returns its running session (no new spawn).
- Make the cap overridable via `SessionManagerOptions` (e.g. `maxSessions?`) with the
  derived default, so tests can pin it.

### Idle-session reaping
- Track per-session last-activity (touch it on acquire/get/chat-adjacent access; pick the
  least intrusive existing call site). After `idleTtlMs` (configurable, sane default e.g. 15
  min) with no activity, reap: `runner.stop(handle)` + `removeWorktree(...)` + drop from the
  `byKey` Map + free the port. Reaping must be safe to call repeatedly and must never reap an
  actively-serving session.
- The reaper can be a timer the manager owns, or a sweep invoked on each acquire; choose the
  simplest correct design and document it. It must not leak timers (clear on stop) and must
  not run in a way that breaks the localhost single-session flow (a single idle session on
  localhost should still reap cleanly, or be exempt if that matches today's behavior; state
  your choice).

## Tests (add; all existing must stay green)
- A `worktree-sessions` fixture (mirror the `__tests__` style, the concat-import `.ts` trick,
  wired into `package.json` `test`) covering: (a) the port allocator returns distinct
  bindable ports and reuses a freed one; (b) the concurrency cap math from a faked
  `os.totalmem()` / `memoryCeilingMb`, and that acquiring beyond the cap returns the typed
  at-capacity outcome while re-acquiring an existing key does not; (c) idle reaping stops +
  removes a session after the TTL and frees its port, and does NOT reap an active one. Use a
  fake/in-memory `Runner` (the `Runner` interface exists precisely so tests inject one) so no
  real `next dev` is spawned.
- The existing `runner.test.mts` (argv + secret-starved env), `tools.fence.test.mts`,
  `tools.editscope.test.mts`, `media.test.mts`, `auth.gate.test.mts`, and the deck-core tests
  MUST all stay green. `pnpm lint` (eslint --max-warnings=0) and `pnpm exec tsc --noEmit`
  clean.

## Definition of done
- The manager runs N concurrent keyed sessions, each on its own dynamic port, capped by host
  RAM, with idle reaping; the localhost single-operator flow is behaviorally unchanged.
- New fixture green; full `pnpm test` + lint + tsc green.
- No push/PR/merge/deploy. No 2.5.2/2.5.3/2.5.4 work. No auth-gate wiring. No infra. File any
  pre-existing issue you notice as an open thread in your final summary rather than fixing
  out of scope.
