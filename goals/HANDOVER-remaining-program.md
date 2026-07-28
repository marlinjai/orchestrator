---
type: handover
status: archived
date: 2026-07-28
summary: Lumitra platform program (workstreams A/B/C). Complete and live-verified 2026-07-28; every engineering item on the pre-launch gate is closed. Superseded by HANDOVER-analytics-multi-company.md.
superseded-by: goals/HANDOVER-analytics-multi-company.md
tags: [authz, auth-brain, storage-brain, analytics, lumitra-studio, pre-launch-gate]
---

# HANDOVER: Lumitra platform program, remaining work (fresh session, agent teams)

> **PROGRAM COMPLETE 2026-07-28.** Every engineering item on the pre-launch gate is closed (items 1-7, 9-11); item 8 is built and waits only on the lawyer review. Workstreams A, B, C1 and C2 all shipped, deployed and live-verified. Beyond the original scope this wave also shipped the company-move machine API, two reconciliation safety fixes, and the B-sync delete half, and restructured the orgs so `marlinjai` is the umbrella.
>
> **Three defects were found that a green CI run could not have caught**, all by post-deploy verification against live systems: workspace-scoped keys could never pass the storage grant door (lola prod storage would have died on its next redeploy); `reconcile --heal` would have deleted the platform-admin tuple and locked the admin console; and shipping the FGA model changed nothing until the manual env flip, so a live over-grant survived the merge. If you take one habit from this program, take that one.
>
> **Open, and all human calls:** delete the 361 orphaned `kie-input` files (review page built, evidence conclusive); the lawyer review of erasure/retention; and the three analytics multi-company design decisions in `goals/HANDOVER-analytics-multi-company.md`, which is the successor document to this one.

> **STATUS UPDATE 2026-07-27, session 2.** Workstream A is DONE except one decision for Marlin. Workstream B is in flight. C1/C2 goal files are written and ready to dispatch once B merges. Read this block before the original text below, which is now partly historical.
>
> **Shipped + deployed + live-verified:** storage-brain#21 (signed-url rate-limit bucketing; ~6% of live requests were 429ing), auth-brain#68 (workspace-scoped keys inherit their company's app_grants), storage-brain#22 (S2 execution record). The `storage` app grant was seeded for the lola-stories company. lola prod's storage key now returns 200 -> tenant lola-stories, where it had been 403ing.
>
> **Workstream A findings that rewrote the slice:** the per-app file split was ALREADY correct in production (20 tenant+context pairs all on the right tenant), so no broad repoint was needed and the shared-key regeneration is moot (nothing borrows the receipts key any more). Key hygiene done: Studio dev, Receipt OCR dev, lola dev/staging all held dead rotated-away keys and now verify 200 against their own tenants; the unused browser-exposed `NEXT_PUBLIC_STORAGE_BRAIN_API_KEY` and the dead `STORAGE_BRAIN_SA_KEY` (scoped to a deleted workspace) were removed.
>
> **OPEN DECISION FOR MARLIN:** 361 orphaned `kie-input` files, 371 MB, 28% of lola's quota. Studio's transient KIE bridge uploads stranded in lola's tenant from the June borrowed-key window; all untagged; the producing code's own comment says the context exists so they can be cleaned up. RECOMMEND DELETE over repoint (repointing would push Studio to 72% quota for files designed to be disposable, and would need a per-context filter added to `repoint-tenant.ts`, which today moves whole tenants only). Not done autonomously because deletion is irreversible.
>
> **Two authz findings the B slice now owns (both verified independently, both in `goals/auth-brain-bsync-inheritance.md`):**
> 1. `workspace.member = this OR admin OR (tenant's MEMBER)` is a live over-grant that decision 1 forbids: every company member is automatically a member of every workspace in that company. Blast radius measured on prod: ZERO users lose access if removed, because all 7 live tenant_memberships are `owner` and no plain `member` role exists yet. Safe to remove now; would bite at first customer onboarding.
> 2. `flows/provisioning.ts` (admin console AND machine API) never emits the structural `tenant.created` / `workspace.created` events, so orgs created that way have NO parent edges in the FGA graph and ALL downward inheritance silently does nothing for them. `provision.ts` (signup) does it right. This is Part 0 of the B goal, with a backfill.
>
> **Operator lessons added this session:** (a) `gh pr merge` run from a worktree fails on local branch cleanup but the MERGE STILL SUCCEEDS: always re-check `gh pr view --json state` before retrying. (b) When a Worker says the goal contradicts the code, CHECK THE GOAL: it happened twice today and the Worker was right both times (I had described the FGA model as flat by listing relation names without their definitions). Stopping and fixing the spec cost minutes; a confidently-wrong diff would have cost far more. (c) auth-brain has NO ops alerting channel of any kind (only `console.error`), so anything needing an alert wires a loop into `packages/app/src/workers/outbox-sync.ts`. (d) Pushing a new FGA model is MANUAL and needs an operator edit to `OPENFGA_AUTHORIZATION_MODEL_ID` in Infisical. (e) Inheritance cannot be tested against the in-memory FGA mock (it cannot evaluate userset rewrites); copy `packages/app/tests/integration/service-account-openfga.spec.ts` which spins up real OpenFGA.

You are the OPERATOR (Claude Code, `autonomous-orchestration` skill loaded, agent teams enabled). Marlin authorized EVERYTHING in this document on 2026-07-27 ("you have my go for everything and everything that deserves the fresh sessions"), INCLUDING the tier-3 auth-brain dispatches named here: cite this when passing `--confirm-stakes`. New tier-3 work outside this list still needs its own go. Read the memory file `authz-decisions-prelaunch-gate.md` first: it holds the standing decisions, ids, and lessons; `goals/MASTER-platform-isolation-program.md` (same dir) documents the completed predecessor program.

## Operating protocol (non-negotiable, learned the hard way)
- Per code slice: worktree off FRESH origin/main -> `orchestrator start` (background, harness-tracked) -> review the diff against `git merge-base HEAD origin/main` (parallel sessions merge to main constantly) -> run the repo's FULL verify chain MATCHING ITS CI EXACTLY (analytics + storage CIs build first) -> gate on EXIT CODES, never `test | grep` -> PR -> CI -> squash-merge -> watch the deploy workflow (names differ: `deploy`, `Build & Deploy`, `Build & Deploy API`) -> live-probe the changed surface -> clean up worktree/branches.
- Dependency bumps: verify `pnpm-lock.yaml` is committed (Workers forget). After pulling merges into a main checkout: `pnpm install` + rebuild workspace dists before trusting local tests.
- Secrets: only via `execute_with_secrets`; same-value two-project secrets are generated server-side; the Infisical project a CONTAINER reads comes from its `entrypoint.sh`, NEVER from a name-based lookup (stale same-named projects exist). Coolify restart after new secrets.
- Tamper flags on runs that deleted/rewrote specs: adjudicate against the goal (ordered deletions are legitimate; check replacement coverage) before trusting or rejecting.
- Use agent teams / parallel subagents for recon and independent review lanes; the orchestrator CLI for code slices; the machine APIs (agent-first) for ALL auth-brain ops: rename/move/delete/grants exist at `/api/admin/machine/*`.

## Workstream A: S2 storage ops (dedicated session, do FIRST while context is fresh)
Plan: storage-brain `docs/plans/2026-07-27-company-isolation.md` incl. the S2 amendment. The problem: several apps borrow the `receipts OCR` SB tenant's key; six per-app SB tenants already exist. Steps:
1. Recon (parallel agents): per-context file attribution in the shared tenant (inventory 2026-07-27: image/kie-input/character-reference/story-*/marketplace-*/voice-* = studio+lola pipelines, receipt = receipts app, flowmap-thumbnail + feedback-screenshot = ATTRIBUTE THESE by searching each consumer repo for the context strings: lumitra-studio, receipt-ocr-app, lola-stories, email-editor, data-table, social-planner). Also inventory which consumer apps hold `STORAGE_BRAIN_API_KEY` in which Infisical projects.
2. Decide the target tenant per context; files whose app is certain move via `scripts/repoint-tenant.ts` (in storage-brain repo: `--map old=new`, transactional, idempotent, EMITS the permanent-URL breakage list: collect it and regenerate links per consumer or accept breakage per the plan's caveat). Ambiguous contexts stay put; document.
3. Mint/regenerate per-app SB tenant keys via the SB admin API (`STORAGE_BRAIN_ADMIN_KEY` lives in the storage Infisical project 86dcae14-6cb2-473b-8b2d-43b37977f04e), swap each consumer's `STORAGE_BRAIN_API_KEY` secret server-side, restart consumers, verify each app's storage flows, THEN regenerate the shared `receipts OCR` tenant key last (kills all borrowed copies at once).
4. Update the plan status + memory.

## Workstream B: gate item 4, B-sync + role inheritance (auth-brain, tier 3, the big one)
Decisions (binding): `auth-brain/docs/plans/2026-07-24-authz-hardening.md` decisions 1+2 and `docs/internal/fga-authoritative-tradeoffs.html`. One slice (or two chained if the Worker's first pass says so):
- Synchronous dual writes: every membership/grant mutation writes Postgres AND its OpenFGA tuple in the SAME request, failing loud; the async outbox path for these tuple writes is retired (outbox stays for audit/mail); nightly reconciliation job diffing Postgres vs FGA with a loud alert channel.
- Inheritance in the FGA MODEL (management roles cascade: org owner/admin -> child tenants -> workspace admin; `member`/`billing_admin` NEVER cascade), evaluated during verify; session/api-key verify payloads deliver EFFECTIVE roles with a `direct` vs `inherited` marker; settings + admin console UIs display the distinction; revision-path tests per the stateful-flow standard.
- SDK/shared minor bumps published post-merge (operator), consumers pinned per need.

## Workstream C: gate items 5+9 (parallel pair, AFTER B merges + SDK publish)
- C1 lumitra-studio: role matrix v1 per the table in `docs/internal/authorization-overview.html` section 05 (destructive -> admin+, spend/work -> member+, keys already owner/admin; read tier ONLY if Marlin has decided the viewer-role product call by then, else build without viewer and leave the row planned). Matrix declared to the suite-apps registry (read-only display in admin console) per decision 3.
- C2 analytics-platform: per-project authorization consolidated onto the verify payload (workspace effective roles from B), removing analytics' direct OpenFGA `can()` calls; FGA remains only for auth-brain's platform-admin gate + future sharing.

## Standing surfacing list (human-only, nag politely every session)
1. Beszel Telegram delivery one-liner (alerts still deliver to NOWHERE; command in the 2026-07-26 chat, or hub UI Settings -> Notifications).
2. Lawyer review of erasure/retention (gate 8 closer).
3. Tenant-level `viewer` role product call (gate 10; blocks part of C1's read tier).
4. After EVERYTHING: update the pre-launch gate table + memory + commit goal files to the orchestrator draft PR branch (`worktree-studio-company-isolation-goals`, PR #13).

Key ids: Lumitra company/tenant `019ec2f2-f19e-70f4-a889-8afb34c314ca` (slug lumitra-core, display "Lumitra"); auth-brain Infisical `97c4971e-...c` / studio `934b272e-...23` / analytics `45b9c32b-...1a` / storage `86dcae14-...4e` / infra `6adabd49-...64` / cc-wrapper `9af620f0-...64`; Coolify apps: auth-brain `h10iicx7b1g7c5dj9z69z4f2`, studio `senas9m9rt0kscipx84w6jfo`, storage API `xsstyh7y5xvkfo13dyg0kvfc`; shared-server-I root SSH `157.90.119.98`, panel host `178.104.60.43`. The `lola-stories` auth-brain WORKSPACE is load-bearing for storage auth: never delete it.
