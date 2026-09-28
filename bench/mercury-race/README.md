---
type: documentation
title: Mercury race benchmark (E4b)
date: 2026-09-28
---

# Mercury race benchmark

The benchmark for phase E4b of `docs/plans/2026-07-24-hexagonal-executor-ports.md`: does Inception's
`mercury-2`, a fast and cheap diffusion model, reach a verified result sooner than Claude when it runs
as the orchestrator's coding Worker? The answer decides whether the Agentic OS milestone M9 (the Mercury
sprint worker) proceeds.

Setup decided by Marlin on 2026-09-28: 10 self-contained goals with hidden tests written for them, the
hidden tests in a verifier folder outside every repo, 2 attempts per goal per cohort, and Mercury wins
only with a lower median time to a verified result AND a hidden-test pass rate within 10 percentage
points of Claude's.

## Layout

| Path | What it is |
|---|---|
| `seed/` | `textkit`, a small text-utilities library every goal starts from. It carries three deliberate bugs (`slugify`, `truncate`, `parse_duration`) for the bug-fix goals. |
| `goals/NN-*.md` | One goal file per task. Each states the required behavior precisely, so the hidden tests judge the spec, not a guess. The frontmatter `verify` runs the visible tests the Worker writes. |
| `heldout/NN-*/` | The hidden tests. `scripts/mercury_race.py run` copies them to `~/.orchestrator/verifier-vault/mercury-race/` and passes that path as `--held-out`, so they sit outside the project the Worker edits. |
| `reference/NN-*/` | A correct solution per goal, overlaid on the seed only by `validate`, to prove each hidden suite is fair. |

Accepted weakness (decision 2 of the page): a Worker's shell runs as the same OS user, so it could
read the vault or this folder. The run logs record every command, so a peek would be visible. Before
racing on real repositories, the hidden tests move to a separate OS user.

## Running it

From the orchestrator repo, with its venv first on `PATH` (the goals and the hidden tests call
`python3 -m pytest`):

```bash
python3 scripts/mercury_race.py validate            # every hidden suite fails on the seed, passes on the reference
python3 scripts/mercury_race.py run --out ~/.orchestrator/mercury-race/<date>
python3 scripts/mercury_race.py report --out ~/.orchestrator/mercury-race/<date>
```

`run` executes every goal twice, once per cohort, as `orchestrator start --best-of 2 --held-out ...`.
The cohorts differ only in their operator config home: the Mercury cohort's `config.toml` pins
`[executors.worker]` to `mercury-2`, the Claude cohort's is empty. `report` writes `report.md` and
`score.json` next to `results.json`; each run's per-attempt `state.json` holds the latency split
(TTFT, generation, tool time, Inception's server time) for the "where did the time go" question.
