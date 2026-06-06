---
task: lola-suggest-uses-child-name
spec: (none — implement from this goal)
---

# Goal

Fix Trello bug "Story creation suggestions is not using the child's name."
Today `POST /stories/.../description-suggestion` only feeds title + age range
to the LLM, so the returned description is generic (no child's name). Users
expect the suggestion to feature THE child(ren) the story is for, by name, so
the description feels personal.

## Scope

End-to-end: backend DTO + service + frontend caller.

## Read first

- `apps/api/src/modules/stories/dto/suggest-description.dto.ts` (current DTO shape)
- `apps/api/src/modules/stories/stories.service.ts` lines 139-179 (suggest implementation)
- `apps/api/src/modules/stories/stories.controller.ts` lines 47-58 (controller wiring)
- `apps/api/src/modules/stories/stories.service.spec.ts` (existing tests for the method)
- Frontend caller(s): `grep -rn "description-suggestion\|suggestDescription\|Aus Titel vorschlagen" apps/web/src`
- Repo CLAUDE.md + `.claude/rules/tdd.md`

## Definition of done

Backend:
- Extend `SuggestDescriptionDto` with `childNames?: string[]` (validated: each item 1-50 chars, max 8 entries, optional). Class-validator decorators per the existing style.
- In `stories.service.ts::suggestDescription`, when `childNames` is provided and non-empty, weave the name(s) into the prompt naturally:
  - de: `Schreibe eine kurze, einladende Inhaltsangabe (2-4 Sätze, 30-60 Wörter) für eine Kinder-Gute-Nacht-Geschichte mit dem Titel "${title}", erzählt für ${joinNames}. Zielalter: ${ageMin}-${ageMax} Jahre. Lass ${joinNames} klar als Hauptfigur(en) auftauchen, skizziere kurz weitere Figuren, Schauplatz und Stimmung. Verwende einfache, warme Sprache.`
  - en: analogous, with `${joinNames}` as the main character(s).
  - Where `joinNames` is a German-locale-aware join: ["Mia"] → "Mia", ["Mia","Leo"] → "Mia und Leo" (de) or "Mia and Leo" (en), 3+ → "Mia, Leo und Anna" / "Mia, Leo, and Anna".
- When `childNames` is omitted or empty, fall back to the current generic prompt (backward compatible).

Tests (TDD, write first):
- Unit test that passing `childNames: ['Mia']` results in `llmService.complete` being called with a prompt containing "Mia" and the personalised phrasing.
- Unit test that passing `childNames: ['Mia','Leo']` produces a prompt joined with "und" (de locale) or "and" (en locale).
- Unit test for backward compat: no `childNames` → existing generic prompt unchanged.
- Validation test: `childNames` of length 9 → 400.
- `pnpm --filter @lola/api test` passes.
- `pnpm --filter @lola/api build` passes (typecheck included).

Frontend:
- Find the caller (likely an "Aus Titel vorschlagen" button on the story-create modal/page). Pass the relevant child name(s) from the form state ("Für welche Kinder?") into the API request body as `childNames`.
- If the form does not yet have access to selected children at the moment of suggestion, surface them via the parent component (props or context). Keep changes minimal: a few prop drills are fine, do NOT introduce a new context just for this.
- `pnpm --filter @lola/web typecheck` passes.
- `pnpm --filter @lola/web build` succeeds (the worker should run this to catch SSR / next.js issues; if too slow, typecheck is acceptable).

Hygiene:
- No em-dashes / en-dashes in new strings or comments (project rule). Use colon, parentheses, comma.
- Single conventional-commit on the branch: `fix(stories): include child names in description-suggestion prompt`.
- Open a PR titled "fix(stories): include child names in description suggestion".
- PR body: Summary + Why + Test plan sections.

## Constraints

- Branch from latest `origin/main` (already fetched at worktree creation).
- Stay in this worktree.
- Do NOT push to main directly. Push the branch and open a PR via `gh pr create`.
- Do NOT touch unrelated files (feedback drawer, family-tree, voice management). Stay scoped.
- Do NOT introduce a new LLM stage name (`description-suggestion` stays the same so attribution / logging stays consistent).
- If you find an existing helper for human-friendly name joining (look in `apps/web/src/lib/` for things like `formatList`, `joinNames`), reuse it rather than re-implementing. Otherwise inline the join in the service.

## Notes

- The Trello card has empty desc — title is the spec: "Bug: Story creation suggestions - is not using the the childs name."
- Locale comes in as either 'de' or 'en' in the DTO; defaults to 'en' otherwise (per current code).
- After commit and PR open, output a final message confirming: branch name, PR URL, files touched count, test count delta.
