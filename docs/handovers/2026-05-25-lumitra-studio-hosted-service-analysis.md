---
type: handover
status: draft
date: 2026-05-25
title: Analyze dependencies for Lumitra Studio as a hosted service, then write the implementation handover
summary: A meta-handover. The receiving session analyzes what "Lumitra Studio as a hosted service" requires against the current framer-clone wave-1 status (8/18 done, some specs blocked on CMS runtime + multiplayer infra), maps spec gaps, then produces a SECOND handover prompt that a fresh implementation session can pick up to write specs and dispatch Workers via the orchestrator.
---

# Handover: Lumitra Studio hosted-service dependency analysis

Paste the section between the fenced lines below into the LolaStories Claude Code session that has been brainstorming Lumitra Studio as a hosted service. The prompt is self-contained (it lists the framer-clone + orchestrator context it might not have) and ends with a clear deliverable: ANOTHER handover prompt suitable for a fresh implementation session.

---

```
# Goal

You've been thinking about turning Lumitra Studio into a hosted service.
Now do a dependency analysis against the current state of the
framer-clone codebase (where Lumitra Studio lives as an editor) and the
existing wave-1 spec backlog. Output a written handover prompt that a
fresh Claude Code session can use to write any missing specs and
dispatch their implementation via the orchestrator.

You are NOT implementing in this session. You are analyzing and
producing the next prompt.

# Context: what already exists

- **framer-clone** at `~/software-dev/ERP-suite/projects/framer-clone`.
  Main branch is at commit `00956c5`, 4 commits ahead of origin
  (`da96f2a`), NOT yet pushed. The recent commits landed Wave 1 specs.
  - 137/137 tests pass at HEAD
  - `pnpm build` green
  - Read `docs/specs/STATUS.md` for the wave delivery ledger and
    `docs/specs/wave-1/*.md` for spec contents
- **Wave 1 status (8 of 18 done):**
  - Done: binding-shape, data-source-provider, component-registry-
    bindable-slots (data-bindings track complete); yjs-doc-shape;
    static-html-data-component-id-fix; lumitra-studio-project-binding
    (the small reserved-fields block on ProjectModel); mst-snapshot-
    serializer; anthropic-sdk-bootstrap
  - Newly unblocked, dispatchable: ai-pattern-a-tool-schema-registry,
    ai-pattern-a-read-tools-and-context, static-html-spike
  - Needs human review before dispatch:
    lumitra-studio-component-id-attribution (overlaps with already-
    landed data-component-id fix at 90672dd)
  - Blocked on the CMS runtime decision (Node vs Workers, Marlin's
    call): cms-service-scaffold, cms-tenant-schema-bootstrap,
    cms-auth-middleware-dual-principal
  - Blocked on hocuspocus infra (human-in-loop): multiplayer-
    hocuspocus-server-scaffold, multiplayer-yjs-mst-binding-slice,
    multiplayer-auth-brain-seam
- **Wave 2 / Wave 3 specs exist** in `docs/specs/wave-2/` and `wave-3/`
  but were not touched in 2026-05 batches. Lumitra-Studio Wave 2
  candidates mentioned in spec frontmatter: snippet-injection,
  settings-panel (these become dispatchable now that project-binding
  landed).
- **Lumitra Analytics** is the existing product at analytics.lumitra.co.
  Lumitra Studio in framer-clone today is the EDITOR side; the
  project-binding spec just reserved fields (`lumitra: { projectId,
  ingestionEndpoint, apiKeyRef, enabled }`) on `ProjectModel` to wire
  studio output to the analytics product later.
- **The orchestrator** at `~/software-dev/orchestrator` (v0.2.0) is the
  autonomous-Worker dispatch tool. The implementation session should
  use it to land the specs you identify. The `autonomous-orchestration`
  Claude Code skill is the operator's playbook. State, telemetry,
  reconciliation all work.

# What "hosted service" probably means (verify your own understanding)

Your prior thinking in this LolaStories session has a concept of what
hosting Lumitra Studio means. Before analyzing, write down in 2-3
sentences:
- Who is the user / tenant?
- What do they get? (an editor URL, an API key, a CMS, a publish
  endpoint, a domain, analytics dashboard wired in?)
- What's NOT in scope? (e.g. multi-region, white-label, on-prem)

This shapes the dependency tree.

# Analysis to perform

1. **Map the hosted-service surface to the current framer-clone
   architecture.** Which existing primitives already exist? Which are
   missing? Be concrete: name files / models / routes.

2. **Walk the dependency tree against wave-1 status.**
   - Does the hosted service need the CMS track to be unblocked?
     (Likely yes for per-tenant content; this is the runtime-decision
     Marlin owes.)
   - Does it need multiplayer / hocuspocus? (Maybe no for v1 if single-
     editor-per-tenant is acceptable; if "co-op contributors editing
     together" is the intended UX, yes.)
   - Does it need ai-pattern-a? (Probably not for the hosting itself,
     but it shapes Studio's value prop.)
   - What lumitra-studio Wave 2 specs are now ready (project-binding
     landed → snippet-injection + settings-panel unblock)? Read them
     in `docs/specs/wave-2/` and assess.

3. **Identify spec gaps.** What specs would need to be WRITTEN, not just
   dispatched? Candidates likely include:
   - Tenant onboarding / signup flow
   - Per-tenant subdomain or path-based routing
   - Billing surface (if not deferred)
   - Publish pipeline (Studio → static hosting → custom domain)
   - Analytics injection on publish (uses the project-binding fields)
   - Editor session auth (different from app-runtime auth)
   For each gap, give it a slug, a 2-paragraph problem statement, and
   note its dependencies on existing wave-1/2/3 specs.

4. **Sequence the work.** What's the minimal slice to hosted-service
   v0.1? What MUST come before each piece? Order by:
   - Architectural prerequisites (CMS runtime decision, hocuspocus
     decision)
   - Spec writing (the ones you identified in step 3)
   - Implementation dispatch (which existing + new specs land in what
     wave)

5. **Flag the architectural decisions Marlin owes** before any of this
   can dispatch. CMS runtime, multiplayer scope, custom-domain
   strategy, billing scope. Each gets one line.

# Deliverable: the implementation-session handover prompt

Write a self-contained prompt the fresh session will paste. It should:
- State the goal of the implementation session in one paragraph
- List specs to WRITE (with slugs, summaries, dependencies) and specs
  to DISPATCH (with their goal-file template starting points)
- Reference the orchestrator + autonomous-orchestration skill so the
  fresh session knows to use them
- Surface the architectural decisions Marlin must answer before
  dispatch (so the fresh session knows when to stop and ask)
- Include Marlin's constraints: typography (no em-dashes / en-dashes),
  Infisical for secrets, no push without confirmation, single conventional
  commit per spec

Save the implementation prompt to:
`~/software-dev/orchestrator/docs/handovers/<DATE>-lumitra-studio-hosted-service-implementation.md`

with proper frontmatter (`type: handover`, `status: draft`, `date`,
`title`, `summary`).

# Constraints for this analysis session

- Do not write code or edit specs in this session. Analysis only.
- Do not push to remote.
- Marlin's typography: no em-dashes (`—`) or en-dashes (`–`) anywhere,
  use colons / parentheses / periods instead.
- Read the actual files before drawing conclusions; don't speculate
  from the spec name alone.
- If you need information you can't find (e.g. how the existing
  Lumitra Analytics product authenticates tenants), record it as an
  "open question for Marlin" rather than guessing.

# Report at the end

When done, output:
1. Path to the implementation handover file you wrote
2. The list of specs to write (slugs + 1-line summaries)
3. The list of architectural decisions Marlin owes
4. Estimated total slices to reach hosted-service v0.1
```

---

## Notes for the analyzing session

- This is a thinking session, not a building session. Resist the urge
  to dispatch a Worker before specs exist.
- Marlin's pace: he prefers one bundled PR over many small ones when
  the scope is a refactor; for fresh feature waves he prefers
  one-spec-per-PR (which is what the orchestrator enforces). The
  hosted-service work is feature-wave, so default to per-spec.
- The framer-clone STATUS.md and wave-1 specs are the source of truth
  for current state. The README field reports in the orchestrator repo
  are historical color, useful for "how did past batches feel" but not
  for "what's the current architectural state."
- If your analysis surfaces something architecturally surprising (e.g.
  "this needs a complete redesign of ProjectModel"), stop and tell
  Marlin BEFORE writing the implementation handover. A wrong handover
  wastes a fresh session.
