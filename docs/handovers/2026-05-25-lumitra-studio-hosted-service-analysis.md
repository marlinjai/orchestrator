---
type: handover
status: draft
date: 2026-05-25
title: Full analysis of Lumitra Studio + framer-clone integration to inform the hosted-service design
summary: A meta-handover. The receiving session must first ground itself in three distinct codebases (Lumitra Studio CLI, the lumitra-studio track inside framer-clone, and analytics.lumitra.co the existing analytics product), then map their actual relationships, only then analyze what "Lumitra Studio as a hosted service" requires. Final deliverable is a SECOND handover prompt that a fresh implementation session can pick up to write specs and dispatch Workers via the orchestrator.
---

# Handover: Lumitra Studio + framer-clone integration analysis

The prior version of this handover assumed framer-clone and Lumitra Studio were the same thing. They are not. Lumitra Studio is a separate localhost-only CLI tool. framer-clone is a visual editor codebase that has a `lumitra-studio` track in its Wave 1 spec backlog, but those specs are about INTEGRATING framer-clone with Lumitra Studio, not about hosting Lumitra Studio itself.

The receiving session must read the actual code in all three places before drawing conclusions.

Paste the section between the fenced lines below into the LolaStories Claude Code session that has been brainstorming Lumitra Studio as a hosted service.

---

```
# Goal

You've been brainstorming Lumitra Studio as a hosted service. Before
producing an implementation plan, you need a grounded analysis of three
distinct codebases and how they relate. Then produce a written handover
prompt that a fresh Claude Code session can use to write any missing
specs and dispatch their implementation via the orchestrator.

You are NOT implementing in this session. You are reading, mapping,
deciding, and writing the next prompt.

# The three things you need to distinguish

The prior session conflated these. Don't repeat that mistake.

1. **Lumitra Studio** (the CLI tool) — currently localhost-only. Lives
   somewhere in Marlin's filesystem; the prior session did not locate
   it. Your first job is to find it. Likely candidates: `~/software-dev/`
   (look for any `lumitra-studio`, `lumitra-cli`, `studio` directory),
   `~/Code/`, `~/dev/`, or as a published package the `lumitra` skill at
   `~/.claude/skills/lumitra/` knows about. The skill description says
   it lets you "create and manage A/B tests, feature flags, and
   experiments via the Lumitra Analytics platform (analytics.lumitra.co)"
   so the CLI talks to that backend. If you can't find it, ask Marlin
   where the source lives.

2. **The `lumitra-studio` track inside framer-clone**
   (`~/software-dev/ERP-suite/projects/framer-clone`). Wave 1 has TWO
   specs in this track: `lumitra-studio-project-binding` (done in 2026-
   05-24 batch, commit `bde156a` on main) and
   `lumitra-studio-component-id-attribution` (still draft, has overlap
   with the already-landed `static-html-data-component-id-fix`).
   Wave 2 has at least two more in the same track per spec-frontmatter
   forward references: `snippet-injection` and `settings-panel`.
   These specs are about WIRING a framer-clone-published site to talk
   to Lumitra Studio. They are NOT about hosting Lumitra Studio. Read
   each spec end to end in `docs/specs/wave-1/lumitra-studio-*.md` and
   `docs/specs/wave-2/lumitra-studio-*.md`.

3. **Lumitra Analytics** (`analytics.lumitra.co`). The production
   SaaS product that already exists. Lumitra Studio (the CLI) talks
   to it. framer-clone-published sites will eventually emit events to
   it. You don't have its source in this filesystem; treat it as a
   black box defined by its public API and the `lumitra` skill.

# Analysis to perform, in order

Skipping or short-circuiting any of these steps produces a wrong
handover. Take the time.

## Step 1: Locate and read Lumitra Studio (the CLI)

Find the source. Read its README, its entry point, its config
file format, how it authenticates to analytics.lumitra.co, and
specifically:

- What does the CLI actually do? (event ingestion? experiment config?
  flag management? something else?)
- Is "localhost-only" a deployment fact (it runs on the user's machine
  and that's the architecture) or a limitation (it COULD be hosted but
  isn't yet)?
- Where does it store state? A local file? A remote DB it already
  talks to?
- What's its install surface today? (binary download, `uv tool install`,
  `npm install -g`, a script?)
- Does it have a programmatic API or only a CLI surface?

Record findings as a "Lumitra Studio: what it actually is" section.

## Step 2: Read the framer-clone integration surface

For each lumitra-studio spec (Wave 1 + Wave 2) in framer-clone, list:

- What problem the spec solves on the framer-clone side
- What it assumes Lumitra Studio provides (API endpoint? SDK? config
  file shape?)
- Where the spec is in its lifecycle (draft / done; if done, the
  commit sha)

Also read the project-binding spec carefully because it landed:
`~/software-dev/ERP-suite/projects/framer-clone/docs/specs/wave-1/lumitra-studio-project-binding.md`
and verify your understanding against the committed code at
`bde156a`.

## Step 3: Map the integration architecture as it exists today

Draw it out (in markdown ASCII or just a labeled list):

- Where does a framer-clone-published site send events?
- Does the snippet it emits hit Lumitra Studio directly, or
  analytics.lumitra.co directly?
- Where does Lumitra Studio sit in the request path?
- What's currently localhost-bound and what's not?

This is the load-bearing diagram for the hosted-service analysis. If
you can't draw it, you don't understand it yet; read more code first.

## Step 4: Define "Lumitra Studio as a hosted service" concretely

The prior LolaStories session that brainstormed this has its own
intent. Write it down in 3-5 sentences:

- Who is the tenant of the hosted service? (Lola Stories? Framer-clone
  end users? Anyone with an API key?)
- What does the tenant get from hosting that they don't get from
  localhost-only? (a stable endpoint? multi-tenancy? team access?
  durability? something framer-clone needs?)
- What stays localhost-only after this change, if anything? (CLI for
  local dev? An "offline" mode?)
- What's NOT in scope? (multi-region, white-label, on-prem)

## Step 5: Dependency tree against current state

Now that you have the architecture grounded, walk the tree:

- Does hosted Lumitra Studio depend on framer-clone changes? Which
  specs?
- Does it depend on the framer-clone CMS track (currently blocked on
  Marlin's runtime decision)?
- Does it depend on framer-clone multiplayer (currently blocked on
  hocuspocus)?
- Does it depend on changes inside Lumitra Studio itself (extract
  the request-handling code from CLI mode into a hostable HTTP server)?
- Does it touch analytics.lumitra.co? (e.g. new endpoints on the
  analytics product to receive multi-tenant studio events)

For each dependency, note:
- Whether the spec exists (and where)
- Whether the spec needs to be WRITTEN (slug + 2-paragraph problem
  statement)
- Whether it's blocked on an architectural decision Marlin owes

## Step 6: Sequence the minimal slice

What's the smallest set of changes that gets you a working hosted
Lumitra Studio v0.1? Order:

1. Architectural decisions Marlin owes (one line each, no more)
2. Specs to write (new ones, with slugs)
3. Specs to dispatch via orchestrator (existing + new)
4. Out of scope for v0.1 but on the road

# Current framer-clone wave status (so you don't need to re-derive)

- Main at commit `00956c5`, 4 commits ahead of origin (`da96f2a`), not
  pushed. 137 tests pass at HEAD.
- Wave 1 done (8 of 18): binding-shape, data-source-provider,
  component-registry-bindable-slots, yjs-doc-shape, static-html-
  data-component-id-fix, lumitra-studio-project-binding, mst-snapshot-
  serializer, anthropic-sdk-bootstrap
- Newly unblocked, ready to dispatch:
  ai-pattern-a-tool-schema-registry, ai-pattern-a-read-tools-and-
  context (after tool-schema-registry), static-html-spike
- Needs human review before dispatch: lumitra-studio-component-id-
  attribution (overlap with static-html-data-component-id-fix at
  `90672dd`)
- Blocked on CMS runtime decision: cms-service-scaffold + 2 dependents
- Blocked on hocuspocus infra: hocuspocus-server-scaffold + 2 dependents

# Tools available to the implementation session you'll hand off to

- **orchestrator** at `~/software-dev/orchestrator` (v0.2.0, pushed to
  `github.com/marlinjai/orchestrator`). Autonomous Worker + Decision
  Proxy loop. Used to dispatch implementation of specs.
- **autonomous-orchestration** Claude Code skill (auto-triggers on
  "autonomous", "dispatch a worker", "launch a batch", etc.). Operator
  playbook for the orchestrator.
- **goals/_template.md** in the orchestrator repo for the goal-file
  starting shape.
- **The handover convention** at `~/software-dev/orchestrator/docs/handovers/`.
  Save the implementation prompt there with frontmatter
  (`type: handover`, `status: draft`, etc.).

# Deliverable: the implementation-session handover prompt

Write a self-contained prompt the fresh session will paste. It should:

1. State the goal of the implementation session in one paragraph
2. Include the "Lumitra Studio: what it actually is" section you wrote
   in Step 1 (the fresh session has zero context; this section gives
   it grounding without re-reading source)
3. Include the integration-architecture diagram from Step 3
4. List specs to WRITE: slugs, 2-paragraph problem statements,
   dependencies on existing specs
5. List specs to DISPATCH (existing draft specs that hosted-service
   needs): slugs and the orchestrator goal-file template path
6. Surface the architectural decisions Marlin must answer BEFORE
   dispatch (so the fresh session knows when to stop and ask)
7. Include Marlin's constraints: typography (no em-dashes / en-dashes
   anywhere, including commits), Infisical for secrets, no push without
   confirmation, single conventional commit per spec

Save the implementation prompt to:
`~/software-dev/orchestrator/docs/handovers/<TODAY>-lumitra-studio-hosted-service-implementation.md`

with proper frontmatter (`type: handover`, `status: draft`, `date`,
`title`, `summary`).

# Constraints for this analysis session

- Do not write code or edit specs.
- Do not push to remote.
- Marlin's typography: no em-dashes (`—`) or en-dashes (`–`) anywhere,
  use colons / parentheses / periods instead.
- Read the actual files in all three codebases before drawing
  conclusions. Speculation from filenames or skill descriptions alone
  produced the prior wrong handover.
- If you cannot locate Lumitra Studio (the CLI), STOP and ask Marlin
  for the path before continuing. Don't substitute "analytics.lumitra.co"
  for it; they are different things.
- If your analysis surfaces something architecturally surprising,
  STOP and tell Marlin before writing the implementation handover. A
  wrong handover wastes a fresh session and burns Marlin's time more
  than it saves it.

# Report at the end

When done, output:
1. Path to the implementation handover file you wrote
2. The "Lumitra Studio: what it actually is" summary in 3-5 sentences
   (so Marlin can sanity-check your grounding before he reads the rest)
3. The list of specs to write (slugs + 1-line summaries each)
4. The list of architectural decisions Marlin owes
5. Estimated total slices to reach hosted-service v0.1
6. Anything you got stuck on or had to defer
```

---

## Notes for the analyzing session (out-of-band, not part of the paste-in)

- This is a thinking session, not a building one. The trap with
  "autonomous" dispatch tools nearby is to start dispatching before
  the specs exist. Resist.
- Marlin's pace: he prefers one bundled PR over many small ones when
  the scope is a refactor; for fresh feature waves he prefers
  one-spec-per-PR (which is what the orchestrator enforces). Hosted-
  service work is feature-wave, so default to per-spec.
- The framer-clone STATUS.md and wave-1 specs are the source of truth
  for the integration side. The README field reports in the orchestrator
  repo are historical color, useful for "how did past batches feel" but
  not for "what's the current architectural state."
- The Lumitra MCP server registered on this machine (per the skill
  list) talks to analytics.lumitra.co. If the CLI source is hard to
  find, the MCP config in `~/.claude.json` or
  `~/software-dev/dotfiles/claude/user-mcp.json` may have a pointer
  to where it lives.
- A previous handover at `2026-05-25-tooling-baseline-bootstrap.md`
  (now status: completed) discovered that `printing-press` is upstream
  at `mvanhorn/cli-printing-press` and `trello` ships via
  `Lola-Stories/trello-pp-cli`. Lumitra Studio may have a similar
  arrangement worth checking before assuming it's a Marlin-only repo.
