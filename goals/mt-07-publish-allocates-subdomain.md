---
task: mt-07
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-06]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-07** (section "MT-07 - Publish route allocates the subdomain + returns the live URL; unpublish route"): wire `ensureSiteDomain` into publish AFTER `publishProject`, return the live `<name>.sites.lumitra.co` URL, and add an unpublish endpoint.

## Read first

- The MT-07 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/app/api/projects/publish/route.ts` — the current flow ends at `saveProject` + `publishProject` and returns `{ siteId, status:'published', publishedPages }`. It imports the shared `projectBodySchema` from `../_schema` (landed by MT-04).
- `src/server/sites/repository.ts` — `ensureSiteDomain(scope, siteId): Promise<{ subdomain }>` and `unpublishProject(scope, siteId)` (landed by MT-06). `publishSite` permission requires `workspace.admin`.
- `src/app/api/projects/save/route.ts` — mirror its structure for the new unpublish route (shape + envelope).
- `src/app/api/projects/__tests__/publish-route.test.ts` — mirror the mocking pattern; `getSiteRepository` mock must now also stub `ensureSiteDomain`/`unpublishProject`.

## Definition of done

Update `src/app/api/projects/publish/route.ts`:
- After `saveProject` + `publishProject`, call `const { subdomain } = await repo.ensureSiteDomain(scope, project.id);`.
- Compute `liveUrl`: read `process.env.PUBLIC_SITE_BASE_HOST`; if set, `liveUrl = ` + a template `https://<subdomain>.<base>`; if UNSET (local dev), `liveUrl = null` (fall back gracefully — still return the `subdomain`).
- Return `{ siteId, status: 'published', publishedPages, subdomain, liveUrl }`.
- An exhausted-collision allocation surfaces a LOUD 500 (the typed `SiteRepositoryError` from MT-06 maps via `siteRepositoryErrorResponse`; any other throw → existing `publish_failed` 500). Never a silent success.

Create `src/app/api/projects/unpublish/route.ts`:
- `export const runtime = 'nodejs'; export const dynamic = 'force-dynamic';`
- `POST` with body `{ siteId: string }` (small zod schema). Guarded flow: `getVerifiedSession` → `resolveActiveScope` → `authenticateRequest(req, scope.workspaceId, 'publishSite')`. Call `repo.unpublishProject(scope, siteId)`. Return `{ siteId, status: 'draft' }`. The `SiteDomain` row survives (MT-06 guarantees it). Full error envelope (401/403/400/404/500).

Tests:
- Re-publishing the SAME site returns the SAME `subdomain`/`liveUrl` (idempotent — assert the mocked `ensureSiteDomain` returns a stable slug and the route surfaces it both times).
- `liveUrl` format: with `PUBLIC_SITE_BASE_HOST=sites.lumitra.co` set, `liveUrl === 'https://<subdomain>.sites.lumitra.co'`; with it unset, `liveUrl === null` and `subdomain` is still present.
- Unpublish: authorizes `publishSite`, returns `{ siteId, status:'draft' }`, the `SiteDomain` row survives, a subsequent re-publish returns the original slug. 401/403/400/404 paths.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(api): publish allocates a stable subdomain + liveUrl; add unpublish route (MT-07)`.

## Constraints

- Stay in this worktree. Files: `src/app/api/projects/publish/route.ts`, new `src/app/api/projects/unpublish/route.ts`, tests. Do NOT change `ensureSiteDomain`/`unpublishProject` (MT-06 owns them).
- Do NOT surface the editor's live URL in `TopBar`/`PublishButton` here — that is MT-12. This spec returns `liveUrl` in the API response only.
- Do not push to any remote. Output a final completion message.

## Notes

- Route test gotcha: `// @vitest-environment node` first line; mock `@/lib/auth-brain`, keep `resolveActiveScope` real, mock `getSiteRepository` (now including `ensureSiteDomain` + `unpublishProject`).
- Keep the env read server-side. Do NOT hardcode `sites.lumitra.co` in the route — read `PUBLIC_SITE_BASE_HOST`.
