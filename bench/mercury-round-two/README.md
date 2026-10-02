---
type: documentation
title: Mercury round two, the race on real repositories
date: 2026-10-02
---

# Mercury round two

Round one (`../mercury-race/`) asked whether Inception's `mercury-2` reaches a verified result sooner
than Claude as the orchestrator's coding Worker, on a toy library written for the purpose. Mercury won.
Marlin decided on 2026-09-28 that a second round on real repositories, with hidden tests the Worker
cannot read, comes before Mercury does real work. This folder is that round. Plan and decisions:
`docs/plans/2026-10-02-mercury-round-two.md`.

Same shape and same exit criterion as round one: 10 goals, a Claude cohort and a Mercury cohort,
2 attempts per goal per cohort, and Mercury wins only with a lower median time to a verified result
AND a hidden-test pass rate within 10 percentage points of Claude's.

## What is here

| Path | What it is |
|---|---|
| `email-editor/` | 5 goals in `marlinjai/email-editor` (the contacts, automation and analytics packages; TypeScript, vitest). |
| `hud/` | 5 goals in the heads-up display app, `apps/hud`, of `marlinjai/agentic-os-platform` (TypeScript, vitest). |
| `<bench>/bench.toml` | Where the base clone is, how a fresh attempt tree is prepared, and the hidden-test command. |
| `<bench>/goals/NN-*.md` | One goal per file: a small, precisely specified change, so the hidden tests judge the spec and not a guess. The frontmatter `verify` runs the package's visible tests. |

| `<bench>/heldout/NN-*/` | The hidden tests of a goal: `files/` (test files as paths relative to the repo root) and `cmd` (the command that runs them). This is the layout of the verifier's vault. |
| `<bench>/reference/NN-*.py` | A correct solution per goal, as a script that patches a tree (`python3 NN-*.py <tree>`), used only to prove the hidden tests fair. |
| `results/` | Report and score of the race of 2026-10-02. |

**Result: Mercury does not pass.** Claude 10 of 10 goals hidden-test green, Mercury 7 of 10; the band
is 10 points. Details and what the misses were: the plan's Result section.

While a race is open the hidden tests and the reference solutions must NOT be in a checkout the
Workers can reach: they run with GitHub access and could clone this repository. They were added here
only after the race of 2026-10-02 had concluded. During a race they live on hermes under
`/var/lib/orch-verifier/vault/<bench>/<goal>/`, readable only by the `orch-verifier` user. A rerun
that is meant to count needs new hidden tests, or a Worker environment without access to this repo.

## How the hidden tests stay hidden

The race runs on hermes. Four things together keep a Worker away from the hidden tests:

1. **Another OS user owns them.** `orch-verifier` owns the vault (mode 700).
2. **A service runs them.** `orch-verify-client <bench> <goal> <tree>` sends one line to the socket
   `/run/orch-verify.sock`; systemd starts `orch-verify` as `orch-verifier`, which copies the tree
   into a private folder, adds the hidden tests, runs them and answers only `PASS` or `FAIL` (a
   failing test prints its assertions, and a Worker's shell can call the client too, so the detail
   goes to a log only `orch-verifier` can read).
3. **The race cannot gain privilege.** The platform user `marlins-hermes` may `sudo` without a
   password and is in the `docker` group, so file ownership alone would stop nothing. The race is
   therefore started through `orch-sandboxed`, a transient systemd unit with `NoNewPrivileges` (sudo
   and su fail) and without the docker, containerd, tailscale and user-systemd sockets.

The scripts, the two systemd units and their runbook are in `agentic-os-platform/deploy/orch-verifier/`.

4. **The tests run as a second user.** They execute the Worker's own code, so they run as
   `orch-runner` in a unit with no network, a read-only file system apart from its work folder and
   no vault access. (Added after the race of 2026-10-02, in which they still ran as `orch-verifier`;
   every attempt's tool log was searched for `orch-verif`, `sudo`, `docker` and `/var/lib` after
   that race, without a hit.)

## Proving the hidden tests fair

On hermes, as root, `orch-prove <bench> <base> '<setup>' <goals-dir> <reference-dir>` checks every
goal: the hidden tests FAIL on an untouched clone, and with the reference solution applied the goal's
visible suite passes and the hidden tests PASS. All ten goals passed this on 2026-10-02.
`<reference-dir>` is `<bench>/reference`, and the vault is filled from `<bench>/heldout`.

## Running it

On hermes, as root (the harness and the Workers then run as `marlins-hermes` inside the sandbox):

```bash
orch-sandboxed orch-race-<date> /srv/orch-race/harness \
  python3 scripts/mercury_race.py run --out /srv/orch-race/out/<date> \
    --bench bench/mercury-round-two/email-editor --bench bench/mercury-round-two/hud
journalctl -u orch-race-<date> -f
```

`/srv/orch-race/harness` is a checkout of this repository; the `orchestrator` on `PATH` is the
installed one. `report --out <dir>` prints the table and the verdict again.
