---
type: plan
title: "Mercury round two: the Claude vs Mercury race on real repositories"
summary: >
  Round one showed Mercury (Inception mercury-2) beating Claude as the orchestrator's coding Worker on
  a toy benchmark. Before Mercury does real work, the same race runs on two real repositories with
  hidden tests owned by a separate OS user on hermes. This plan records Marlin's five decisions, how
  the hidden tests are kept out of a Worker's reach on a host where the platform user may sudo, and
  the result.
status: in-progress
date: 2026-10-02
owner: marlin
tags: [mercury, executor, race, held-out, hermes]
related:
  - docs/plans/2026-07-24-hexagonal-executor-ports.md
  - bench/mercury-round-two/README.md
---

# Mercury round two

## Why

`docs/plans/2026-07-24-hexagonal-executor-ports.md` ended with the verdict "Mercury wins" on the
textkit benchmark (both cohorts 10 of 10 hidden-test green, Mercury several times faster and about
29 times cheaper). Marlin decided on 2026-09-28 that a round on real repositories, with hidden tests
a Worker cannot read at all, comes before Mercury does real work, for example as the Worker behind
an Agentic OS sprint on hermes.

## Decisions (Marlin, 2026-10-02, decision page `decision-pages/2026-10-02-mercury-round-two.html`)

1. **Repos**: `marlinjai/email-editor` and the heads-up display app (`apps/hud`) of
   `marlinjai/agentic-os-platform`, 5 goals each.
2. **Goals and hidden tests**: written by Claude, proven fair, run; Marlin gets the list with the
   results. Every attempt lands on a throwaway clone, nothing is merged.
3. **Hidden tests**: on hermes, owned by a new system user `orch-verifier`; the platform user reaches
   them only through one fixed verifier command.
4. **Secrets proxy**: the existing hermes machine identity joins the proxy's gate project
   (`infra#53`, applied 2026-10-02), so Mercury calls can leave hermes.
5. **Worker shell on hermes**: accepted for round two; Workers running as their own low-privilege
   user is a gate before Mercury does real work on hermes (home: agentic-os-platform `ROADMAP.md`).

The exit criterion is unchanged from round one: at least 10 goals, 2 attempts per goal per cohort,
Mercury wins only with a lower median time to a verified result and a hidden-test pass rate within
10 percentage points of Claude's.

## What turned out differently from the decision page

Decision 3 assumed a sudoers rule ("marlins-hermes may run exactly one verifier script as that
user"). On hermes that would have protected nothing: `marlins-hermes` already has unrestricted
passwordless sudo and is in the `docker` group, so a Worker's shell could become root and read the
vault whatever its owner. Changing Marlin's own sudo setup on a production host was not on the page
and was not done. Instead:

- The verifier is a socket-activated systemd service (`/run/orch-verify.sock`), so asking for a
  verification needs no privilege change at all.
- The race is started through `orch-sandboxed`: a transient systemd unit that runs as
  `marlins-hermes` with `NoNewPrivileges` (sudo, su and every setuid program fail) and without the
  docker, containerd, tailscale and user-systemd sockets. Probed on 2026-10-02: all of those fail
  inside the unit, while the verifier, the Mercury forward, Claude and the orchestrator work.

So within the race the hidden tests are out of reach by prevention, not only by ownership. This is
also the first working piece of decision 5: the same launcher can wrap the platform's Worker runs.

Remaining exposure, stated plainly: an attempt's tests execute the Worker's own code as
`orch-verifier`, so code written to read the vault during verification could. The verifier answers
only PASS or FAIL, and every attempt's tool log is checked after the race.

## How it is built

- **Goals**: `bench/mercury-round-two/<bench>/goals/`. Each is a small change in a pure-logic module
  (an operator, a parser rule, an option, an error case), specified precisely.
- **Hidden tests and reference solutions**: on hermes only while the race is open
  (`/var/lib/orch-verifier/vault`, root's reference folder), because Workers have GitHub access and
  could clone this repository. Committed here once the race has concluded.
- **Fairness proof**: `orch-prove` (root, hermes): hidden tests fail on an untouched clone; with the
  reference solution the visible suite passes and the hidden tests pass. 10 of 10 on 2026-10-02.
- **Harness**: `scripts/mercury_race.py run --bench <dir>`. A repo bench runs its own attempts (a
  fresh clone per attempt, the bench's setup command, one `orchestrator start` with the bench's
  hidden-test command), because a best-of worktree would start without the repo's installed
  dependencies. Scoring, the 10-point band and the report are the round-one code, unchanged.
- **Host pieces** (verifier script, client, socket units, sandbox launcher, proof script, runbook):
  `agentic-os-platform/deploy/orch-verifier/`.

## Verification

- Unit tests for the manifest loader and the repo-bench runner (`tests/test_mercury_race.py`).
- The fairness proof above.
- The sandbox probe above.
- After the race: every attempt's `worker-tools.jsonl` (Mercury) and transcript (Claude) is searched
  for `orch-verif`, `sudo`, `docker` and `/var/lib`; a hit outside the orchestrator's own gate
  invalidates that attempt.

## Result

Recorded here when the race has run.
