---
type: handover
status: draft
date: 2026-05-25
title: Analysis of Lumitra Studio CLI to inform its hosted-service design
summary: A meta-handover. The receiving session reads the Lumitra Studio CLI source at ~/software-dev/ERP-suite/projects/lumitra-studio, maps what's localhost-bound vs hostable, defines the hosted-service v0.1 surface, and produces a SECOND handover prompt that a fresh implementation session can pick up. framer-clone is explicitly NOT in scope; the cross-integration is a future Wave 2+ concern.
---

# Handover: Lumitra Studio hosted-service analysis

The receiving session is the Claude Code session already brainstorming Lumitra Studio as a hosted service. This handover provides the missing context it needs (the canonical Lumitra product taxonomy, where the source lives, what the hosting initiative IS NOT) and defines the deliverable.

Paste the section between the fenced lines below.

---

```
# Goal

You've been brainstorming Lumitra Studio as a hosted service. Now do
a grounded analysis against the actual Lumitra Studio source code,
define the hosted-service v0.1 surface concretely, and produce a
written handover prompt that a fresh Claude Code session can use to
write specs and implement them.

You are NOT implementing in this session. You are reading, mapping,
deciding, and writing the next prompt.

# Product taxonomy (read this first, do not conflate)

Three things have "Lumitra" in their name. They are different products:

1. **Lumitra Analytics**: existing SaaS at analytics.lumitra.co. A/B
   tests, feature flags, experiments, event ingestion. The `lumitra`
   Claude Code skill and `lumitra` MCP both talk to THIS. Out of
   scope for this analysis.

2. **Lumitra Studio**: a separate CLI tool at
   `~/software-dev/ERP-suite/projects/lumitra-studio`. **This is the
   one being hosted.** Currently localhost-only. Generates images and
   visuals via the KIE image API and Google APIs under the hood.

3. **framer-clone**: a visual editor codebase at
   `~/software-dev/ERP-suite/projects/framer-clone`. **Out of scope
   for this analysis.** Note: framer-clone has a Wave 1 spec track
   with `lumitra-studio-*` slugs (e.g. `lumitra-studio-project-binding`).
   Those slugs are misleadingly named. They are about wiring
   framer-clone to Lumitra Analytics (the SaaS), NOT to Lumitra Studio
   the CLI. Ignore them for this analysis. Cross-integration (framer-
   clone users calling hosted Lumitra Studio for AI image generation
   inside the editor) is a separate Wave 2+ initiative that comes
   AFTER Lumitra Studio is hostable.

For your work in this session, only #2 matters.

# Analysis to perform, in order

## Step 1: Read the Lumitra Studio source

Open `~/software-dev/ERP-suite/projects/lumitra-studio` and read end
to end:

- README, package manifest (package.json / pyproject.toml / Cargo.toml
  / etc.), entry-point script
- The command surface: what subcommands exist? what arguments? what
  config?
- The KIE and Google API integration code: how does it authenticate,
  what does it send, what does it receive?
- Local state: where is anything stored, cached, or written? (filesystem
  paths, sqlite, in-process memory only?)
- Concurrency model: single-shot CLI invocation per call, or is there
  a daemon mode?
- Any existing configuration that hints at "hostability" (env vars,
  config files, plugin points)

Write a "Lumitra Studio: what it actually is" section in 5-7 sentences.
Include: language/runtime, install surface today, command surface,
backends it calls, where it keeps state, what's per-user vs per-machine.

## Step 2: Identify what's localhost-bound vs hostable

For each piece of functionality, decide:

- **Already host-ready:** code that has no implicit localhost assumption.
  Stateless calls to external APIs, clear input/output contracts.
- **Localhost-bound but extractable:** code that assumes filesystem
  access, local processes, or user-bound auth, but could be rewritten
  to be host-friendly without changing the product.
- **Fundamentally localhost:** code that doesn't make sense as a hosted
  service (e.g. UI that runs in the user's terminal). Decide whether
  hosting means moving this functionality elsewhere or simply not
  offering it via the hosted version.

Output a table or list with each piece classified.

## Step 3: Define hosted-service v0.1 concretely

Write down in 5-8 sentences:

- **Tenant model:** who has an account? What's a "user" vs an "org"?
  Single-user with API keys, or full multi-tenant with teams?
- **Surface:** REST? gRPC? Both CLI-tunnel and HTTP? Just HTTP with
  an OpenAPI spec?
- **Auth:** API key per tenant? OAuth? Both? How are keys created,
  rotated, revoked?
- **State:** does the hosted version need a database for tenants,
  keys, usage history? Or is it stateless besides upstream KIE/Google?
- **Rate limiting + cost control:** since each request hits paid
  upstream APIs (KIE, Google), how is per-tenant usage tracked and
  capped?
- **What's NOT in v0.1:** white-label, team collaboration, custom
  models, billing surface (or scope billing in if it's load-bearing
  from day one), webhooks, etc.

## Step 4: Map dependencies and architectural decisions

For each part of the hosted-service design above, note:

- Does it depend on Lumitra Analytics? (e.g. usage events flow there)
- Does it depend on infrastructure decisions Marlin owes? (Coolify
  vs Vercel, database choice, secret management, custom domain
  strategy)
- Does it depend on changes to the CLI itself? (e.g. extracting the
  image-generation core into a library both the CLI and the hosted
  service can import)

Each decision gets one line. Marlin's standing infra: Coolify on
Hetzner for app hosting, Infisical for secrets, Cloudflare for DNS.

## Step 5: Identify specs to write

For each piece of work the hosted-service v0.1 needs, decide whether
a spec exists somewhere or whether one needs to be written. Likely
candidates for new specs:

- Hosted service scaffold (HTTP layer, deployment, health checks)
- Tenant + API key model
- Per-tenant usage tracking + rate limiting
- Migration of the image-generation core to a hostable library
- Hosted-service auth flow (signup, key creation, rotation)

For each new spec, give it a slug, a 2-paragraph problem statement,
and note its dependencies on existing or other new specs.

## Step 6: Sequence the minimal slice

What's the smallest set of changes that gets a working hosted
Lumitra Studio v0.1? Order by:

1. Architectural decisions Marlin owes (so the fresh session knows
   when to stop and ask)
2. Specs to write (the new ones from Step 5)
3. Specs / code changes to implement (which existing CLI code needs
   refactoring, what new code lands first)

# Tools the fresh implementation session will have

- **orchestrator** at `~/software-dev/orchestrator` (v0.2.0, pushed to
  `github.com/marlinjai/orchestrator`). Autonomous Worker + Decision
  Proxy loop. Dispatches implementation of specs.
- **autonomous-orchestration** Claude Code skill (auto-triggers on
  "autonomous", "dispatch a worker", etc.). The operator playbook.
- **goals/_template.md** in the orchestrator repo for the goal-file
  starting shape.
- **The handover convention** at
  `~/software-dev/orchestrator/docs/handovers/`. Save the
  implementation prompt there with frontmatter (`type: handover`,
  `status: draft`, etc.).

# Deliverable: the implementation-session handover prompt

Write a self-contained prompt the fresh session will paste. It must:

1. State the implementation session's goal in one paragraph
2. Include the "Lumitra Studio: what it actually is" section you
   wrote in Step 1 (the fresh session has zero context; this section
   gives it grounding without re-reading source)
3. Include the localhost-bound-vs-hostable classification from Step 2
4. Include the v0.1 surface definition from Step 3
5. Surface the architectural decisions Marlin owes (from Step 4)
6. List specs to WRITE: slugs, 2-paragraph problem statements,
   dependencies
7. Sequence the implementation work (from Step 6)
8. Marlin's constraints: typography (no em-dashes / en-dashes
   anywhere, including commits), Infisical for secrets, no push
   without confirmation, single conventional commit per spec, Coolify
   + Hetzner for app hosting

Save the implementation prompt to:
`~/software-dev/orchestrator/docs/handovers/<TODAY>-lumitra-studio-hosted-service-implementation.md`

with frontmatter (`type: handover`, `status: draft`, `date`, `title`,
`summary`).

# Constraints for this analysis session

- Do not write code or edit specs.
- Do not push to remote.
- Marlin's typography: no em-dashes (`—`) or en-dashes (`–`) anywhere,
  use colons / parentheses / periods instead.
- Read the actual Lumitra Studio source before drawing conclusions.
  Speculation from filenames or skill descriptions alone produced a
  prior wrong handover that Marlin had to correct.
- If your analysis surfaces something architecturally surprising
  (e.g. "Lumitra Studio actually IS just a wrapper around KIE and
  the hosting is trivial" or "this needs a fundamental redesign before
  it's hostable at all"), STOP and tell Marlin before writing the
  implementation handover.

# Report at the end

When done, output:
1. Path to the implementation handover file you wrote
2. The "Lumitra Studio: what it actually is" summary in 5-7 sentences
   (so Marlin can sanity-check your grounding before reading the rest)
3. The list of NEW specs (slugs + 1-line summaries)
4. The list of architectural decisions Marlin owes
5. Estimated slice count to reach hosted-service v0.1
6. Anything you got stuck on or had to defer
```

---

## Notes for the analyzing session (out-of-band, not part of the paste-in)

- This is a thinking session, not a building session. The trap with
  "autonomous" dispatch tools nearby is to start dispatching before
  the specs exist. Resist.
- A prior version of this handover wrongly framed the analysis as
  needing to read framer-clone alongside Lumitra Studio. That was
  hallucinated. framer-clone is not in scope. The corrected taxonomy
  is in `~/.claude/projects/-Users-marlinjai/memory/project_lumitra_taxonomy.md`
  if a future session needs to look up the disambiguation.
- Marlin's pace: he prefers one bundled PR over many small ones when
  the scope is a refactor; for fresh feature waves he prefers
  one-spec-per-PR (which is what the orchestrator enforces). Hosted-
  service work is a mix: the initial scaffold + extracts may be
  bundled refactors, then per-spec feature waves after.
- Marlin's infra defaults: Coolify on Hetzner for app hosting,
  Infisical for secrets, Cloudflare for DNS, Terraform for declarative
  setup. Reference the `scaffold-project` skill if the hosted service
  needs a fresh deploy stack.
- A previous handover at `2026-05-25-tooling-baseline-bootstrap.md`
  (status: completed) discovered that several Marlin tools are
  upstream'd to other accounts (printing-press at
  `mvanhorn/cli-printing-press`, trello binary via
  `Lola-Stories/trello-pp-cli`). Worth checking if Lumitra Studio
  has a similar arrangement before assuming it's a Marlin-only repo.
