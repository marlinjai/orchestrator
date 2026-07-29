---
task: discovery-feeder-intents
verify: bats tests/discovery_feeder.bats
# Verify is bats (bootstrap's harness). Adapter = a stdlib-only python3 script
# (clean JSON->markdown), tested by a NEW tests/discovery_feeder.bats that invokes it
# with a fixture strategy.json and asserts the emitted intent-stub frontmatter + idempotency.
# Target repo (--project): ~/software-dev/marlinjai-bootstrap  (the drain + adapter live here;
#   the intent stubs it writes land in ~/software-dev/knowledge-base/backlog/intents/)
# Wave 1 / leaf L5. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 3: "Proactive discovery feeder" / Wave 1 glue)
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L5)
depends_on: [drain-lib-extraction]
shared_state: [drain, intents]
---

# Goal

Re-home the salvageable `researcher` + `strategist` agents from the (now-retired) product-evolution
skill as a WEEKLY discovery-feeder drain that drops value/cost-scored intent stubs into
`knowledge-base/backlog/intents/`. It FEEDS the backlog and NEVER dispatches: its only output is
draft intent-stub markdown that `/sweep` then ranks alongside human-authored intents. This is the
proactive-discovery layer of the platform, scoped to "produce scored stubs", not "run anything".

## Read first

- The salvage source: `modules/claude-skills-contributor/skills/product-evolution/agents/researcher.md`
  and `agents/strategist.md`, plus `references/schemas.md` (the `opportunities.json` / `strategy.json`
  shapes: value 1-10, cost/effort 1-10, ratio, tags, source_ids). Reuse the prompts + scoring; drop the rest of the product-evolution loop (task-gen / worker / critic are OUT of scope).
- The target convention: `~/software-dev/knowledge-base/backlog/intents/*.md` (frontmatter: `id`,
  `status: draft`, `leverage`, optional `blocked_by`; body cites evidence). Look at an existing stub, e.g.
  `backlog/intents/lumitra-fx-visual-verification-and-promise-rejection.md`, and match it EXACTLY.
- `/sweep`: `modules/claude-skills-marlin/skills/sweep/SKILL.md` (the canonical projection that re-renders `backlog.md` from intents + plans). Confirm a researcher-authored stub is picked up with no sweep change; if a small recognition tweak is needed, make it minimal.
- `drain-lib.sh` (from L1, leaf `drain-lib-extraction`): the drain wrapper MUST consume it (init/lock/log/spawn-headless), not re-duplicate the capture-drain patterns. The existing `capture-drain.sh` + `com.marlinjai.capture-drain.plist` are the shape to mirror (weekly cadence, not 15-min).

## Scope

1. **Adapter** (new, the substantive logic): a small module that takes the strategist's scored output
   (the `strategy.json` shape) and emits one intent-stub markdown file per item into
   `backlog/intents/`, with frontmatter matching the live convention (`id` slugified from the title,
   `status: draft`, `leverage` mapped from the value/cost ratio: HIGH/MEDIUM/LOW), a body that carries
   the description + evidence + value/cost/ratio, and a provenance line marking it discovery-feeder-authored
   and dated. Idempotent: never overwrite an existing stub with the same `id` (append-store semantics).
2. **The drain wrapper** (new `scripts/discovery-feeder.sh`): sources `drain-lib.sh`, takes the lock,
   runs the researcher + strategist headlessly (over a product/repo summary input), pipes their output
   through the adapter, logs, releases the lock. ~20-30 lines on top of the library.
3. **Weekly launchd plist** (`launchd/com.marlinjai.discovery-feeder.plist`): a 7-day cadence timer,
   mirroring the capture-drain plist's env setup. Document the install step; do not auto-load it as part of the build.
4. **Tests** for the adapter (the only part with real logic): given a fixed `strategy.json` fixture,
   assert the emitted stub's frontmatter + body match the convention, the slug is stable, leverage
   mapping is correct, and a second run over the same input writes nothing new (idempotent). Use the
   repo's existing test harness (pytest if the adapter is Python; BATS if it is shell) -- pick the simplest that fits the adapter's language.

## Definition of done

- The adapter converts a `strategy.json` fixture into convention-correct intent stubs in `backlog/intents/`; idempotent over re-runs.
- `discovery-feeder.sh` is a thin caller on `drain-lib.sh` (no duplicated lock/log/headless logic) and the weekly plist exists + is documented (not auto-loaded).
- A researcher-authored stub is shown to be picked up by `/sweep`'s projection (note how it ranks; no sweep regression).
- `uv run pytest tests/ -q` (or `bats tests/`, per the adapter's language) is green; the adapter tests prove convention-match + idempotency.
- A short note in the relevant module README: what the feeder does, that it FEEDS and never dispatches, and the weekly-install step.
- Single conventional commit describing the WHY (proactive discovery that feeds the backlog, never dispatches).

## Constraints

- Stay in this worktree; do not push. The feeder NEVER dispatches anything and NEVER writes outside `backlog/intents/` (+ its own script/plist/test files).
- Salvage ONLY researcher + strategist. Do NOT re-home the product-evolution task-generator, worker, or critic (the roadmap retires that loop).
- Every emitted stub is `status: draft` -- a human (or `/sweep`) decides; the feeder only proposes.
- The drain wrapper consumes `drain-lib.sh`; do not copy capture-drain's patterns inline (that is the tech debt L1 exists to delete).
- No em-dashes / en-dashes (including in generated stub bodies). Conventional-commit message.

## Notes

- `depends_on: drain-lib-extraction` -- the wrapper sits on `drain-lib.sh`, so this leaf's drain-script
  portion MERGES after L1. The adapter + its tests are independent and can be built in parallel; only the
  final wrapper wiring waits on L1.
- product-evolution is already gone locally; the salvageable source lives ONLY in the skill dir named in "Read first". Extract-and-reuse the prompts; do not try to clone a missing repo.
- Scoring stays value/cost as the agents already define it; do not invent a new scoring scheme (the one decision metric for DISPATCH is the human's, not the feeder's).
