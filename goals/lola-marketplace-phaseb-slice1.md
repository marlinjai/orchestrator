---
task: lola-marketplace-phaseb-slice1
spec: docs/specs/2026-05-26-marketplace-phaseb-slice1-lumitra-studio-client.md
depends_on: [lola-marketplace-phaseb-specs]
shared_state: [env]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice1-lumitra-studio-client.md` end-to-end. This stands up the Lumitra Studio HTTP client as its own NestJS module and adds an admin-only smoke endpoint so the integration is verifiable end-to-end against `studio.lumitra.co` before slice 7 wires it into the real cover-image flow.

## Read first

- The spec file (full contents: Goal, File Structure, Implementation, API surface, Test plan, Definition of done, Out of scope, Dependencies)
- The parent plan section "External Integrations -> Lumitra Studio" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/api/src/config/env.validation.ts` (existing Zod schema; you will extend it)
- `apps/api/src/modules/admin/admin.controller.ts` (existing admin guard usage; mirror that pattern for the smoke endpoint)
- An existing NestJS module in this repo to mirror the structure (e.g. `apps/api/src/modules/llm/` or `apps/api/src/modules/feedback/`)
- `.claude/rules/tdd.md` (Red-Green-Refactor, co-located `.spec.ts`, mocked PrismaService where applicable)
- `~/software-dev/ERP-suite/projects/lumitra-studio/scripts/smoke-deploy.ts` for the reference shape of the polling loop (do NOT import from there; reimplement in our own service so we control the surface). The smoke test is the canonical example of how to POST, poll, and read costUsd from the upstream API.

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes (or whichever turbo task runs the API package's tests in this repo; verify by reading `package.json` and `turbo.json`)
- `pnpm --filter @lola/api tsc --noEmit` clean
- `pnpm build` clean for the workspaces touched
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(api): lumitra-studio client module + admin smoke endpoint`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Do not edit any file outside `apps/api/src/` or `apps/api/src/config/env.validation.ts` or the spec file's `status:` line. NO changes to web, infra repos, or lumitra-studio repo.
- Env vars `LUMITRA_STUDIO_BASE_URL` and `LUMITRA_STUDIO_SERVICE_TOKEN` are operational concerns and live in Infisical; the code only references them via the Zod-validated env. Document in the spec / commit message that these need to be added to Infisical /apps/api /prod before the smoke endpoint will work in production, but do NOT attempt to add them yourself.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output. Use colons, parentheses, commas, periods.
- Mocked `fetch` in unit tests via `vi.stubGlobal` (vitest) or the Jest equivalent — whichever this repo uses (verify by reading an existing test).
- The polling loop must cap at 6 minutes (KIE's internal poll is 5 min plus network slack). Do not block the request thread; return `{jobId, pollUrl}` and let the caller poll a status endpoint, OR (if you keep it synchronous as the spec suggests) the smoke endpoint is the ONLY caller and is admin-only, so a 6-min hold on one connection is acceptable. Follow the spec's chosen shape.

## Notes

- The consumer-side `LUMITRA_STUDIO_` prefix is correct here (unlike inside the lumitra-studio project itself). See `project_lumitra_studio_v0_1_deploy.md` for the rationale: the prefix disambiguates the upstream service from lola-stories' own service tokens.
- If anything in the spec is unclear or contradicts current repo conventions, prefer the repo conventions and add an `open_thread` entry via `update_state` describing the deviation. Do NOT stop and ask.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
