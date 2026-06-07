---
task: doc-reconciliation
verify: bash -c "ls research/*reconciliation*.md && ls research/*remediation*.md && ls research/*clearify*.md"
verify_timeout_s: 120
verify_fix_cap: 2
worker_allowed_tools: [Task]
---

# MISSION

Reconcile and make coherent all documentation, plans, and their relationship to actual
implementation across every repository under ~/software-dev, and research how Clearify
should serve as the public-facing documentation platform (including git-based inline
editing). This is the foundational hygiene pass that PRECEDES building a cross-project
orchestration backlog: it produces the clean, claim-verified, trustworthy intent layer that
backlog will later derive from. This is READ-AND-PROPOSE only. Do not execute cleanup.

# ORCHESTRATOR-SPECIFIC SETUP (read carefully)

- Your project (cwd) is a git worktree checkout of the `knowledge-base` repo. The ONLY files
  you may create or modify are the three deliverable docs, written to `research/` in THIS
  worktree (relative path `research/...`). Commit them here. Do not touch anything else in
  this worktree.
- You READ every other repository at its normal path under `~/software-dev/<repo>` (for
  example `~/software-dev/arbosano`, `~/software-dev/lola-stories`, `~/software-dev/MedusaJS`,
  `~/software-dev/ERP-suite` and its `projects/*`, etc.). Those reads are READ-ONLY. Never
  modify, move, delete, commit, or run cleanup in any repo other than writing your three docs
  in this worktree.
- USE SUB-AGENTS (the Task tool) to fan out: spawn one sub-agent per repository (cluster the
  tiny repos) for the per-repo audit, plus a dedicated sub-agent for the Clearify research,
  then synthesize their structured findings yourself. Do not attempt all 25 repos serially in
  one context. Each sub-agent returns structured findings; you merge and write the docs.

# CONTEXT

- ~25 repos under ~/software-dev. A prior scan found 621 plan-like docs; ~274 are
  completed/archived, the rest a mix of live plans, perma-draft research/spikes, and ephemeral
  session HANDOVERS never archived. Directories conflate durable plans, dead handovers,
  research, and completed work. Handover sprawl is the dominant noise (e.g. arbosano
  "Handover #2/#3/#4/#5" chains where only the latest is live).
- READ FIRST: ~/software-dev/knowledge-base/standards/document-lifecycle.md (the source of
  truth for doc types readme/documentation/plan/roadmap/changelog; plan statuses
  draft|decided|in-progress|completed|archived|rejected; path inference; graceful fallbacks).
  Also ~/software-dev/knowledge-base/standards/package-naming.md.
- KNOWN FAILURE MODE: plans that CLAIM done/merged but are NOT (a prior analytics session
  falsely reported a fix). Verify every claim against git/code. Trust only what YOU confirm.
- Clearify (@marlinjai/clearify, repo at ~/software-dev/ERP-suite/projects/clearify) is the
  intended public-facing docs platform and a declared consumer of the document-lifecycle
  frontmatter (title/summary/description/tags/status/order/icon/date/projects).

# PHASES

1. PER-REPO INVENTORY + CLASSIFICATION (sub-agent per repo): inventory every markdown doc;
   classify by type per the standard (plans by status); flag missing/inconsistent frontmatter,
   misclassified docs, docs in the wrong location, handovers masquerading as durable plans,
   superseded handover chains, and completed/superseded docs never marked archived.
2. CLAIM-vs-REALITY (the hard part, per repo): for every plan marked in-progress or completed,
   VERIFY its claims against the actual repo (git log, branches, merged PRs, the code/features).
   Output per plan: claimed status vs verified status + evidence. Catch false-done. For
   decided/draft plans: still relevant, or superseded/stale?
3. README + CORE-DOCS FRESHNESS (per repo): is each README accurate against the current code,
   structure, scripts, and package name (per package-naming)? Flag stale/missing READMEs and
   exactly what is wrong.
4. TAXONOMY COHERENCE (cross-repo synthesis): assess how consistently the document-lifecycle
   standard is actually applied. Identify systemic gaps (handovers have no distinct treatment
   and pollute the plan space; no archival discipline; inconsistent directories). Propose a
   concrete uniform taxonomy + directory convention to apply across ALL repos, and whether the
   STANDARD ITSELF needs extending (e.g. a first-class handover/ephemeral treatment, an
   archival rule).
5. CLEARIFY RESEARCH (dedicated sub-agent): read the Clearify repo + its docs. Determine how it
   was intended to be used as the public docs platform, what frontmatter it consumes/renders,
   and its current state. Then research + propose: (a) git-based inline editing (edit a doc in
   the Clearify UI, commit back to the source git repo), and (b) Clearify as the HUMAN
   editing+viewing front-end for the git "durable intent" layer (plans + docs) that the
   cross-project backlog derives from, vs the session-dashboard as the operational read model.
   Cite the Clearify code.

# DELIVERABLES (write to research/ in this worktree; prefix filenames with 2026-06-07; no em-dashes or en-dashes)

1. research/2026-06-07-doc-reconciliation-audit.md : per-repo findings (inventory,
   claim-vs-reality discrepancies WITH evidence, README status) + the cross-repo taxonomy
   assessment.
2. research/2026-06-07-doc-remediation-plan.md (frontmatter type: plan, status: draft) : which
   docs to archive/reclassify/relocate, which plan statuses to correct (with evidence), README
   fixes, and the uniform taxonomy + directory convention. NOTHING executed without Marlin's
   approval.
3. research/2026-06-07-clearify-public-docs-direction.md (frontmatter type: plan, status:
   draft) : how Clearify is/should be used, the git-inline-editing proposal, and its role as
   the human front-end to the intent layer.

# DEFINITION OF DONE

All three deliverable docs exist in research/, are complete and internally coherent, and the
audit's claim-vs-reality section cites concrete evidence (commits, branches, PRs, code paths)
for every status correction it proposes.

# CONSTRAINTS

- Read-only against all repos except writing your three docs in this worktree. Propose, do not
  execute cleanup, do not modify implementations, do not move or archive files.
- Trust only verified facts; explicitly flag anything you cannot confirm.
- No em-dashes or en-dashes anywhere. Never print secret values into the docs.
- Structure outputs so the claim-verified plan inventory can seed a cross-project orchestration
  backlog later.
