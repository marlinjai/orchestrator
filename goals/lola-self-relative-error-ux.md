---
task: lola-self-relative-error-ux
spec: (none — implement from this goal)
---

# Goal

Fix Trello bug `6a16c3b945b0ac899d786e2b` ("Error code shouldn't be visible here"). During onboarding on `/en/dashboard` after the "Setting up your family..." progress screen, end users currently see this developer-facing error rendered as plain page content:

> Error: Family is missing SELF relative — backend may not have bootstrapped it

That string is from a debug branch / fallback in the family-bootstrap flow and should never reach a user. Fix on two axes: (1) prevent the underlying condition where possible by retrying bootstrap, (2) replace the visible string with a graceful user-facing UX when retry exhausts.

## Read first

- Locate the literal: `grep -rn "Family is missing SELF relative\|missing SELF\|backend may not have bootstrapped" apps/web apps/api packages` — should find both the throw site and the render site.
- Family bootstrap path: probably `apps/api/src/modules/families/*` (look for bootstrap, ensureSelf, ensureBootstrap). The "SELF relative" is the Person node representing the account-holding user — created on family creation per Phase 1b (PR #120).
- Onboarding flow on `/en/dashboard`: `apps/web/src/app/[locale]/dashboard/` and any layout that renders "Setting up your family...". The error is rendered after that progress bar finishes.
- Memory: `project_family_tree_redesign.md` references Phase 1b/Person/RelationshipGraph. Phase 1b shipped via PR #113 (additive schema) + PR #120 (app rewire). The "SELF" concept came in then. Likely missed bootstrap is a race condition or migration gap.

## Definition of done

Backend (apps/api):
- The bootstrap of a family's SELF Person is idempotent and recoverable. If a family is fetched and lacks a SELF, the read path should either: (a) lazy-bootstrap on read and return the now-correct payload, OR (b) return a structured 409/422 with a machine-readable code so the frontend can call a `POST /families/:id/bootstrap` endpoint and retry. Pick whichever is closer to the current architecture.
- Add an endpoint or extend an existing one so the frontend can self-heal without the user seeing a raw string.
- Log the underlying cause (which family ID, which user, what state) with a unique log code so we can grep for occurrences.

Frontend (apps/web):
- The onboarding "Setting up your family..." screen must NOT render developer-facing strings on failure. Three states:
  - **success**: continue to the next onboarding step.
  - **transient/retryable**: show a generic "Just a moment, finishing setup..." with a spinner, automatically retry up to 3 times with exponential backoff (500ms / 1.5s / 4s).
  - **fatal**: show a calm friendly error card with "Something went wrong setting up your family. Please try again or contact us." plus a Retry button and a Support link.
- Internationalised: BOTH `de.json` and `en.json` for any new user-facing string.

Tests:
- Backend: unit test that fetching a family without SELF triggers lazy bootstrap (or returns the structured error). Test that bootstrap is idempotent.
- Frontend: component test for the three states (success / retrying / fatal). Don't actually fire timers; mock them.
- All existing `pnpm --filter @lola/api test` and `pnpm --filter @lola/web test` pass.

Conventional commit: `fix(onboarding): graceful UX when family SELF bootstrap is missing`.

## Constraints

- Branch from `origin/main`.
- Stay in worktree. Push branch + open PR via `gh`. Do not push to main.
- Don't try to "clean up" the family-tree code beyond what this bug requires. Scope discipline.
- The fix MUST handle both: (i) the race where bootstrap raced behind initial fetch, (ii) older families in DB that never got SELF (data gap). Don't assume either is impossible.

## Notes

- Reference screenshot at `/tmp/feedback-shots/error-code-2.png` (main session only — you cannot read it from worker).
- The error showed on `/en/dashboard` after a 100% progress bar — meaning the frontend believes setup finished. So either: setup did finish but the read path doesn't trust the result, OR setup partially failed silently and the read path catches it via the SELF check. Investigate which.
- Final message: branch, PR URL, list of touched files, count of new tests, mention of whether you went lazy-bootstrap or structured-error+retry route.
