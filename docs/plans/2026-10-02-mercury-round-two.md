---
type: plan
title: "Mercury round two: the Claude vs Mercury race on real repositories"
summary: >
  Round one showed Mercury (Inception mercury-2) beating Claude as the orchestrator's coding Worker on
  a toy benchmark. Before Mercury does real work, the same race runs on two real repositories with
  hidden tests owned by a separate OS user on hermes. This plan records Marlin's five decisions, how
  the hidden tests are kept out of a Worker's reach on a host where the platform user may sudo, and
  the result: Mercury does not pass (7 of 10 goals hidden-test green against Claude's 10 of 10).
status: completed
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
- **Hidden tests and reference solutions**: on hermes only while the race was open
  (`/var/lib/orch-verifier/vault`, root's reference folder), because Workers have GitHub access and
  could clone this repository. Committed here after the race (`<bench>/heldout`, `<bench>/reference`).
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

## Result (race of 2026-10-02): Mercury does not pass

Run on hermes inside the sandbox, 10 goals, 2 attempts per goal per cohort, 40 attempts in all. Data:
`bench/mercury-round-two/results/` (report and score) and, in full, `~/.orchestrator/mercury-race/2026-10-02-round-two/`.

| Goal | Claude | Mercury |
|---|---|---|
| email-editor-01-segment-numeric | pass 68.0s | pass 31.8s |
| email-editor-02-merge-fallback | pass 66.3s | pass 28.2s |
| email-editor-03-condition-operators | pass 77.8s | pass 34.8s |
| email-editor-04-engagement-clock | pass 45.5s | pass 96.1s |
| email-editor-05-csv-edges | pass 62.2s | FAIL |
| hud-01-notes-under-options | pass 49.6s | pass 33.2s |
| hud-02-notion-cover-roundtrip | pass 43.2s | FAIL |
| hud-03-switch-company-errors | pass 46.7s | pass 27.6s |
| hud-04-number-and-duration | pass 76.9s | FAIL |
| hud-05-youtube-start | pass 68.6s | pass 33.0s |

| | Claude | Mercury |
|---|---|---|
| Goals hidden-test green | 10 of 10 | 7 of 10 |
| Attempts hidden-test green | 20 of 20 | 14 of 20 |
| Median time to a verified result (best attempt per goal, a failed goal counts as infinitely slow) | 64.2s | 34.0s |
| Attempt time, median | 65.1s | 66.5s |
| Attempt time, mean | 63.7s | 78.4s |
| Attempts finished in one iteration | 20 of 20 | 20 of 20 |
| Estimated cost, all 20 attempts | 12.42 USD | 1.57 USD |

**Verdict by the pre-registered criterion: Mercury does not win.** Its median time to a verified
result is lower, but its hidden-test pass rate is 30 points below Claude's, and the band is 10.

What the misses are. Each of the three failed goals failed the same single hidden test in both
attempts, and each time it is an edge case the goal states in so many words:

- `email-editor-05-csv-edges`: a field ending in a quoted part must keep the whitespace inside the
  quotes (` a "b " ` is `a b `, example-level rule 3 of the goal); Mercury trimmed it. 13 of 14 pass.
- `hud-02-notion-cover-roundtrip`: the upload name must normalise the extension (surrounding
  whitespace, leading dots, case, `jpeg` to `jpg`); one of the listed normalisations was missed.
  7 of 8 pass.
- `hud-04-number-and-duration`: a signed value inside accounting parentheses, or parentheses that do
  not wrap the whole value, must give `null`; Mercury returned a number. 42 of 43 pass.

So Mercury gets the main behavior right every time and drops one stated rule in a longer spec.
Its own visible tests passed in all 20 attempts, which is exactly the case the hidden tests exist
for: green by its own account, wrong by the spec. On round one's toy library this did not show.

Speed. Per attempt Mercury was no faster than Claude on real repositories (median 66.5s against
65.1s). The time is the provider: a median of 30s of Inception server time per attempt over a median
of 23.5 model calls, with a wide spread (28s to 193s per attempt). The "faster" half of the criterion
is met only because best-of-2 picks the quicker attempt.

Integrity. No attempt of either cohort touched `sudo`, `docker`, the verifier or `/var/lib` (all 20
Mercury tool logs and all 20 Claude transcripts searched). The verifier answered every request.

## Consequence

Mercury is not cleared for real work as a coding Worker. It stays available behind the held-out
gate (which is what caught these misses), and the orchestrator's default Worker stays Claude. The
Agentic OS line "Mercury as the sprint Worker on hermes" does not proceed on this result; whether to
try again under other conditions (a higher `reasoning_effort`, a spec-checklist step before the
Worker stops, a newer Mercury model) is Marlin's call and is recorded under the platform's
"Decisions needed".

The hidden tests and the reference solutions are in `bench/mercury-round-two/<bench>/heldout` and
`reference` now that the race is closed, so the round can be rerun with
`scripts/mercury_race.py run --bench ...` after `orch-prove`.
