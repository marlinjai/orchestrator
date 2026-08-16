---
task: sp-ai-captions
depends_on: [sp-test-harness]
shared_state: [lockfile, env]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Phase 2 of the social-planner design doc: AI captions and hashtags. In the post detail
panel, generate an Instagram caption from the image plus the project's brand voice,
suggest hashtags, and offer rewrite / shorten / translate DE<->EN quick actions.

Spec: `docs/plans/2026-07-12-social-planner-design.md`, section 7.2.

## Read first

- `docs/plans/2026-07-12-social-planner-design.md` sections 5, 7.2 and 15
- `prisma/schema.prisma`: `Project.brandVoice`, `Project.defaultLanguage`,
  `Post.caption`, `Post.hashtags`, `Post.language`. **These already exist. This slice
  needs NO schema change and NO migration.**
- `src/components/admin/PostDetailPanel.tsx` (where the actions belong)
- `src/lib/storage.ts` (how media is fetched from Storage Brain)
- `src/lib/auth.ts` and an existing route under `src/app/api/` for the auth pattern
- The test harness added by the `sp-test-harness` slice: follow its mocking
  conventions rather than inventing new ones

## Definition of done

- Server-side API routes under `src/app/api/ai/` for: **caption**, **hashtags**, and
  **transform** (rewrite / shorten / translate). All authenticated with the existing
  `requireApiAuth` guard. The Anthropic call happens server-side only; the key must
  never reach the client bundle.
- Uses the `@anthropic-ai/sdk` package and the model id **`claude-sonnet-5`**. Do not
  substitute another model id.
- Caption generation is **vision-based**: it sends the actual image (fetched from
  Storage Brain) plus the project's `brandVoice` and target language, and returns a
  caption in that language and voice.
- Hashtags return a deduped mix of broad-reach and niche tags, derived from the image
  and caption, as a structured list the UI can accept or edit individually.
- Transform supports rewrite, shorten, and translate between German and English,
  operating on the caption already in the panel.
- `PostDetailPanel` gets the UI for all of it: a generate button per action, a visible
  loading state, and the result written into the existing caption / hashtags fields so
  the user can edit before saving. Nothing auto-saves without the user's action.
- **Errors surface, never swallow.** A failed or rate-limited Anthropic call shows the
  user an actionable message and leaves their existing text untouched. Do not fall back
  to silently returning an empty caption.
- Reads `ANTHROPIC_API_KEY` from the environment. It is already scaffolded in Infisical
  (social-planner project, prod, path `/`) and injected at container boot by
  `entrypoint.sh`. Do NOT hardcode it, do not add it to any committed file, and do not
  print it.
- Tests, mocking the Anthropic SDK (no real API calls in the suite): each route
  rejects unauthenticated requests, builds the expected request shape (correct model,
  image content block present for caption, brand voice and language included), parses
  a successful response, and surfaces an API error rather than swallowing it.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** The app is live at
  social.lumitra.co.
- Do not change `prisma/schema.prisma`. Every field this slice needs already exists.
- Do not build scheduling, the cron tick, the publish queue, or Resend email. That is
  the next slice.
- Never make a real Anthropic API call from a test.

## Notes

- The key in Infisical is currently the placeholder `PLACEHOLDER_REPLACE_IN_UI`, so the
  feature will not produce real captions until Marlin fills in the real value. Build and
  test against a mocked SDK; that is expected and is not a blocker for this slice.
- Brand voice is stored per project precisely so output stays consistent without
  re-prompting each time. Read it from the project, do not ask the user to paste it.
- Marlin posts bilingually (German and English), so language handling is a first-class
  requirement here, not an afterthought.
- If you spot Phase 1 bugs while wiring the panel, fix the small clear ones and file
  anything larger with `update_state(kind="open_thread")`.
