---
task: sp-reels-upload
shared_state: [lockfile, prisma, migrations]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Support **Reels** (video) in social-planner: upload a video, get a poster frame
and duration, see it in the media browser and the feed-preview grid marked as a
reel, and plan/caption/schedule it like any other post.

Today the upload route calls `sharp(bytes)` unconditionally, so a video upload
throws. The original design doc listed Reels as a v1 non-goal; Marlin has since
asked for them explicitly (2026-08-16), so this is a deliberate scope decision,
not scope creep.

## Read first

- `src/app/api/projects/[slug]/media/route.ts`: the image-only upload path you
  are generalizing (note the company-prefixed Storage Brain `context`, keep it)
- `prisma/schema.prisma`: `Media`, `Post`
- `src/lib/storage.ts`, `src/lib/ai.ts`, `src/lib/ai-routes.ts`
- `src/components/admin/MediaBrowser.tsx`, `PreviewGrid.tsx`, `PostDetailPanel.tsx`
- `Dockerfile` and `next.config.ts`: read the sharp/libvips comments before
  touching either. They document a real production outage caused by a native
  dependency missing from the traced output; do not regress that.
- `docs/plans/2026-08-16-multi-tenancy.md`: every new query MUST stay
  company-scoped exactly like the rest.

## Definition of done

- **Schema + migration**: `Media.mediaType` (`"image" | "video"`, default
  `"image"` so existing rows are correct), `Media.durationMs Int?`. Reels are a
  post format, so also `Post.format` (`"feed" | "reel"`, default `"feed"`).
- **Upload accepts video** (`video/mp4`, `video/quicktime`) alongside images.
  Branch on the detected type; never run `sharp` over a video.
- **Poster frame + probe via ffmpeg**, invoked as a binary through
  `child_process` (do NOT add a heavyweight wrapper dependency): extract a frame
  (~1s in, or the midpoint for very short clips) as the thumbnail, and read
  width, height and duration. The poster goes through the SAME Storage Brain
  thumbnail path images use, so the grid stays uniform.
- **ffmpeg present in the image**: add it in the Dockerfile (`apk add --no-cache
  ffmpeg`) AND verify it at build time (`ffmpeg -version`), mirroring how the
  sharp sidecar makes a missing native dependency a loud BUILD failure instead of
  a silent runtime one. This repo has already been burned once by exactly that.
- **Validation, with actionable errors** (never a generic 500): reject an
  unsupported mime type, reject a file over a sane size cap (pick one, ~200MB,
  and state it in the message), and reject a video longer than 90s with a message
  naming Instagram's Reels limit.
- **UI**: the media browser renders the poster with a clear video/reel marker and
  the duration; the feed-preview grid shows the poster with the same marker
  (Instagram shows reels in the grid too); the post detail panel previews the
  video with a native `<video controls>` rather than a broken `<img>`.
- **AI captions work for a reel**: caption from the POSTER FRAME (Claude vision
  takes images, not video). The existing caption/hashtag/transform routes must
  keep working for a video-backed post rather than erroring.
- **Company scoping is preserved everywhere.** Every new or changed query filters
  by the session's company, and any new by-id lookup verifies ownership first.
  Add the same cross-company test for any route you touch.
- Tests: image upload still works unchanged; video upload creates a `video` row
  with a poster, duration and dimensions; unsupported type, oversize file and
  over-90s video each rejected with their specific message and no storage write;
  caption route works for a video-backed post using the poster. Mock ffmpeg and
  Storage Brain, no real binaries or network in tests.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** The app is
  live at social.lumitra.co with real tenants.
- Do not weaken or delete existing tests to get a green build.
- Do not build auto-publishing to Instagram. Publishing stays assisted, and the
  scheduler does not exist yet.
- Do not regress the sharp/libvips fix or the company-scoping guarantees.

## Notes

- Reels are 9:16; the feed grid is square. Center-crop the POSTER for the grid
  thumbnail, keep the original untouched. Do not re-encode the video itself.
- Whole-file buffering is how images work today. For a 200MB video that is heavy;
  if you can stream to Storage Brain without a large refactor, do; if not, keep
  buffering, state the tradeoff in the commit message, and file an
  `update_state(kind="open_thread")` rather than silently shipping a memory
  problem.
- Instagram limits worth encoding now: Reels up to 90s, MP4/MOV, H.264 + AAC.
- The scheduler and publish queue (Phase 3) do not exist yet. A reel just needs
  to plan and caption correctly; publishing it is the assisted flow later.
