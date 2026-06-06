---
task: lola-relation-mother-father
spec: (none — implement from this goal)
---

# Goal

Fix Trello bug `6a16c33f860741e7e8e722bb` ("That's to grandmother, grandfather, mother, father. The rest is fine."). On the onboarding "Who are you to <child>?" relationship picker, the generic options `Parent` and `Grandparent` need to split into gendered variants: `Mother` / `Father` and `Grandmother` / `Grandfather`. The other options (`Aunt`, `Uncle`, `Sister`, `Brother`, `Godparent`, `Family friend`, `Other`) stay exactly as they are.

Why: downstream story generation needs the relation's grammatical gender (memory rule `feedback_german_gendering_reliable.md` — "every person-referring German string respects gender"). A generic "Parent" cannot drive correct German pronouns / story narration; "Mother" vs "Father" can.

## Read first

- Find the picker: `grep -rn "Who are you to\|Wer bist du für\|Grandparent\|Großeltern" apps/web/src --include="*.tsx" --include="*.ts"` — likely under `apps/web/src/app/[locale]/.../onboarding/` or `apps/web/src/components/onboarding/`.
- The screenshot shows it lives on `/en/dashboard` (post-signup family-setup flow). Path indicates an onboarding step that runs against an account that has not yet completed family setup.
- `apps/web/messages/de.json` + `apps/web/messages/en.json` under whichever key holds the relation labels.
- Repo `CLAUDE.md`, `.claude/rules/tdd.md`, the family-tree types in `packages/types` or `apps/web/src/lib` (Person/RelationshipGraph from Phase 1b).
- Backend: the relation enum probably lives in `apps/api/src/.../family*.ts` or in `@prisma/schema.prisma`. Find it.

## Definition of done

Frontend (apps/web):
- The relationship picker on the onboarding step ("Who are you to <child>?") shows: `Mother | Father | Grandmother | Grandfather | Aunt | Uncle | Sister | Brother | Godparent | Family friend | Other`.
- The selected value maps to a gendered relation type sent to the backend.
- i18n: BOTH `de.json` and `en.json` updated with the new labels. Existing keys for Parent/Grandparent removed (or repurposed) if no other UI consumes them. Run `pnpm --filter @lola/web i18n:check`.
- No em-dashes / en-dashes in new strings (project rule). German keeps proper `\uXXXX` escaping.

Backend (apps/api):
- The relation enum / Prisma model accepts the gendered values (`MOTHER`, `FATHER`, `GRANDMOTHER`, `GRANDFATHER`, plus the existing AUNT/UNCLE/SISTER/BROTHER/GODPARENT/FAMILY_FRIEND/OTHER). If the enum currently has PARENT and GRANDPARENT, expand it; do NOT remove old values yet (some existing rows in dev/prod DBs may use them). Add a Prisma migration that just adds the new enum values.
- The `RelationshipGraph` / Person derivation logic (Phase 1b family rewire) handles the new values for "mother of", "father of", "grandmother of", "grandfather of" relationships correctly. Cross-check `family-graph` builders.

Tests:
- Unit test on the picker component: rendering all expected labels, dispatching the right relation type when each is clicked.
- Service / resolver test that the new enum values flow through end-to-end (`POST /family-memberships/relations` or whichever endpoint this hits).
- Existing tests must still pass. `pnpm --filter @lola/web test`, `pnpm --filter @lola/api test`.

Backwards compat:
- Existing Person rows with `relation: PARENT` or `relation: GRANDPARENT` should not break. Either: (a) leave the old enum values in the schema as deprecated (preferred), (b) write a one-shot migration that infers gender from `person.gender` and updates the column. Choose (a) unless very confident in (b).

Conventional commit: `fix(family): split Parent/Grandparent into gendered Mother/Father/Grandmother/Grandfather`.

Open PR titled the same. Body: Summary + Why (gendered story-gen) + Test plan.

## Constraints

- Branch from `origin/main` (worktree already set up at that tip).
- Stay in worktree, push branch + open PR via gh, never push to main.
- Don't widen scope to other relation polish work even if you notice it. File an `open_thread` if you do.
- If you find that the relation enum lives in `@lola/types` (workspace pkg), update there + cascade — don't duplicate.

## Notes

- Project memory `project_family_tree_redesign.md` and `feedback_german_gendering_reliable.md` are relevant context.
- The screenshot of the bug is captured at `/tmp/feedback-shots/relation-bug.png` (mainline session) — referenced for context only; you cannot read it from inside the worker. Just trust this goal file's verbal description.
- After commit + PR open, final message must include: branch name, PR URL, files touched count, list of new enum values shipped.
