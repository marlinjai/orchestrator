---
type: handover
status: draft
date: 2026-05-25
title: Lumitra Studio internal-infra deploy v0.1 implementation
summary: Implementation handover for deploying Lumitra Studio (Next.js + CLI image/3D asset generator at ~/software-dev/ERP-suite/projects/lumitra-studio) as private internal infrastructure on Coolify/Hetzner. NOT a SaaS. Single shared bearer token, one tenant (Marlin), consumed by lola-stories admin and other Marlin apps. Three slices to working v0.1.
---

# Handover: Lumitra Studio internal-infra deploy v0.1

Paste the section between the fenced lines below into a fresh Claude Code session. The prompt is self-contained: the receiving session has zero prior context.

**Why this is internal infra and not a SaaS:** the full reasoning lives in `~/software-dev/ERP-suite/projects/lumitra-studio/docs/plans/2026-05-25-hosted-shape-decision.md`. Short version: KIE.ai already exists as an API-based image-gen wrapper, so a third-party SaaS Lumitra Studio would compete weakly. The deploy value is centralization across Marlin's own apps (one model catalog, one provider-key surface, one brand library, one cost dashboard), plus making Studio callable from browser contexts (lola-stories admin) where Vertex/KIE keys cannot ship to. Marlin's other private infra (Storage Brain) follows the same pattern.

---

```
# Goal

Deploy Lumitra Studio at
`~/software-dev/ERP-suite/projects/lumitra-studio` as private internal
infrastructure on Coolify/Hetzner so Marlin's other apps (lola-stories
admin, framer-clone editor, future Lumitra products) can call it for
image and 3D asset generation. This is NOT a SaaS. One tenant (Marlin),
one shared bearer token, no signup, no quotas, no admin UI, no billing.

Three things have "Lumitra" in the name. They are different products:

1. **Lumitra Analytics**: existing SaaS at analytics.lumitra.co (A/B
   tests, flags, experiments). Env vars: `LUMITRA_ANALYTICS_*`. Skill:
   `lumitra-analytics`. Out of scope.
2. **Lumitra Studio**: the thing you are deploying (this prompt). Env
   vars: `LUMITRA_STUDIO_*`. No skill yet.
3. **framer-clone**: separate visual editor codebase. Out of scope. Its
   Wave 1 specs include slugs like `lumitra-studio-project-binding`
   which are about wiring framer-clone to Lumitra Analytics (#1), NOT
   to Lumitra Studio (#2). Ignore them.

**Naming discipline (non-negotiable):** never use bare `LUMITRA_*` for
new env vars or identifiers. Always `LUMITRA_STUDIO_*` for anything
this deploy touches.

## Lumitra Studio: what it actually is

Next.js 16 app plus three TypeScript CLIs at
`~/software-dev/ERP-suite/projects/lumitra-studio`. Brand-aware AI
asset generation (images + 3D meshes) backed by Postgres + Prisma +
pg-boss + Storage Brain SDK. Providers: Vertex AI (Imagen 4, Gemini
Image variants) and KIE.ai (Nano Banana 2, Imagen 4 Fast, Seedream
V4). Domain models: Project, Session, Message, Asset (with parent +
derivedFromIds across Image / Model3D / Material / Texture / etc.),
Job. Today it is single-user localhost: `pnpm dev` boots Next.js, the
in-process pg-boss worker lazy-starts on first `/api/generate`,
brand definitions live on filesystem under `brands/<slug>/`, secrets
arrive via `infisical run`, no user auth.

The only deep localhost binding is the brand filesystem. Everything
else is host-ready: HTTP API exists, Postgres is already remote,
binary assets already flow to Storage Brain. For internal-infra v0.1
the brand filesystem stays on disk (one tenant = one filesystem;
revisit when a second tenant is real).

## v0.1 surface

- **Tenant model:** one tenant (Marlin). No accounts, no signup, no
  ApiKey table.
- **Auth:** single bearer token (`LUMITRA_STUDIO_SERVICE_TOKEN` env
  var, Infisical-injected) checked by Next.js middleware on `/api/*`.
  Same token shared across all consumer apps for v0.1. Health route
  `/api/health` stays public for Coolify liveness checks.
- **State:** existing Postgres schema, no migrations needed beyond
  baseline.
- **CLIs:** the existing repo-local `pnpm generate` / `pnpm remove-bg`
  / `pnpm library` stay as-is (lib-direct mode, your laptop's
  Infisical-injected creds). No remote CLI yet; consumer apps call
  the HTTP API directly with the service token.
- **NOT in v0.1:** tenants, ApiKey tables, NextAuth, quotas, rate
  limiting, admin UI, BYOK, brand DB migration, custom domains,
  billing, multi-region, webhooks, public signup. Deferred until a
  paying customer materializes.

## Architectural decisions Marlin owes before dispatch

Stop and ask before dispatching specs that depend on these. Each one
line:

1. **Lib extraction (`@marlinjai/lumitra-core`)**: do it as slice 1
   (recommended, opens future paths and small effort), or defer
   entirely until a second consumer needs the lib path?
2. **Domain**: `studio.lumitra.co` (public DNS) or Coolify-internal
   hostname (private, only reachable from other Coolify apps on the
   same server)?
3. **Worker scaling**: keep lazy in-process worker (recommended for
   one-tenant scale) or split worker process now?
4. **Postgres**: new Coolify-managed Postgres instance for this app,
   or share with an existing instance via a separate schema/database?

## Specs to WRITE

For each spec below: write under `docs/specs/` in the lumitra-studio
repo (create the directory if missing), one file per spec, slug as
filename, frontmatter (`type: spec, status: draft, date, title,
summary`). After writing all specs, commit them as one conventional
commit (`docs(specs): internal-infra deploy v0.1 spec set`). Then
dispatch implementation per the sequence below.

### `lumitra-core-library-extraction` (P0, optional)

Extract a `packages/lumitra-core` workspace from the existing
`src/lib/providers/`, the filesystem-free version of `src/lib/brand.ts`
(takes a `brandRootDir` argument instead of resolving via
`__dirname`), and the Zod schemas from `src/lib/jobs/types.ts`.
Publishable to npm as `@marlinjai/lumitra-core` (private or public
per Marlin's call). The Next.js app imports from
`@marlinjai/lumitra-core`.

This is mostly mechanical: relocate files, adjust import paths, add a
package.json with `tsup` build. The brand loader gets a small
refactor to accept the root directory as a parameter so consumers can
choose their own brand location (filesystem path for repo-local
usage, or in the future a DB-backed loader). Skip this spec entirely
if Marlin chose "defer" on architectural decision #1.

Depends on: nothing.

### `service-token-auth-middleware` (P0)

Next.js middleware at `src/middleware.ts` that checks
`Authorization: Bearer <token>` against `LUMITRA_STUDIO_SERVICE_TOKEN`
(from `process.env`, injected via Infisical in production). Applied
to all `/api/*` routes except `/api/health`. On miss: 401 with JSON
`{ error: 'unauthorized' }`. On match: pass through. Token comparison
uses constant-time compare to avoid timing leaks.

`/api/health` is a new route returning
`{ status: 'ok', db: <ping>, queue: <pg-boss status> }` for Coolify
liveness. No auth, no tenant context.

This is single-token check, not multi-key lookup. No database read on
the auth path. If/when a second tenant ever exists, swap this
middleware for a real ApiKey table lookup; for now KISS.

Depends on: nothing. (If extracting `lumitra-core`, this lives in the
Next.js app, not the lib.)

### `coolify-deploy` (P0)

Production deploy infra following Marlin's standing pattern
(reference `scaffold-project` skill and `project_infisical_runtime_injection.md`
memory):

- Dockerfile: Next.js standalone build + Sharp + pnpm. Multi-stage
  build, distroless or slim-bullseye base. Infisical CLI installed
  in runtime stage. Entrypoint script runs `infisical run` wrapping
  the Next.js start command (canonical runtime injection pattern,
  same as lola-stories API).
- Coolify app on Hetzner. New Infisical project named
  `lumitra-studio`. Coolify pulls GHCR image, Infisical sync at
  boot.
- Managed Postgres (new instance OR shared schema per Marlin's
  decision #4). Connection string into Infisical as
  `LUMITRA_STUDIO_DATABASE_URL`.
- Infisical secrets to provision: `LUMITRA_STUDIO_SERVICE_TOKEN`
  (generate fresh), `LUMITRA_STUDIO_DATABASE_URL`,
  `LUMITRA_STUDIO_STORAGE_BRAIN_API_KEY`,
  `LUMITRA_STUDIO_STORAGE_BRAIN_ENDPOINT`, `KIE_API_KEY`,
  `GOOGLE_APPLICATION_CREDENTIALS_JSON` (the Vertex service account
  JSON inlined; entrypoint writes it to a temp file and sets
  `GOOGLE_APPLICATION_CREDENTIALS` to the path).
- DNS at `studio.lumitra.co` via Cloudflare (or Coolify-internal
  hostname per decision #2). SSL via Coolify automation.
- CI/CD via GitHub Actions on main: build, push to GHCR, hit Coolify
  webhook. Follow lola-stories API deploy workflow pattern.
- Healthcheck wired to `/api/health` at the Coolify layer (NOT only
  in the Dockerfile; document the gotcha from
  `reference_coolify_storage_brain_deploy_gotchas.md`).
- After first deploy: smoke test from your laptop using the live
  service token. Generate one image. Confirm asset lands in Storage
  Brain. Confirm cost row in `Job` table.

Depends on: `service-token-auth-middleware`. Last slice in the chain.

## Implementation sequence

| Slice | Spec | Notes |
|---|---|---|
| 0 | (decisions block) | Marlin answers the 4 architectural decisions above. No dispatch until done. |
| 1 (optional) | `lumitra-core-library-extraction` | Skip if Marlin chose defer on decision #1. |
| 2 | `service-token-auth-middleware` | Small. Single PR. |
| 3 | `coolify-deploy` | The real deploy. Final slice. Smoke test from laptop. |

Estimated total: **3 to 5 evening sessions** to working v0.1
(depending on whether slice 1 is in scope).

## Tools to use

- **orchestrator** at `~/software-dev/orchestrator` (v0.2.0). Dispatch
  each spec's implementation as an autonomous Worker. Goal files in
  `goals/`; `goals/_template.md` is the shape.
- **autonomous-orchestration** Claude Code skill. Auto-triggers on
  "dispatch a Worker", "kick this off in the background", etc.
- **scaffold-project** skill for the deploy slice (Coolify + Hetzner +
  Infisical + DNS).
- **storage-brain SDK** is already a dependency.

## Marlin's constraints

These are non-negotiable. Bake them into every spec and every commit.

- **Typography**: no em-dashes (`—`) or en-dashes (`–`) anywhere,
  including specs, commits, PR descriptions, code comments. Use
  colons, parentheses, commas, periods. Hyphens in compound words
  are fine.
- **Naming**: `LUMITRA_STUDIO_*` for all new env vars. Never bare
  `LUMITRA_*`. Disambiguates from Lumitra Analytics
  (`LUMITRA_ANALYTICS_*`) and other Lumitra products.
- **Secrets**: Infisical only. Never commit `.env`, `.env.local`, or
  secrets to settings.json. `.infisical.json` gitignored. Runtime
  injection via Docker entrypoint.
- **Pushing**: never `git push` without explicit Marlin confirmation.
  Branches stay local until asked.
- **Commits**: one conventional commit per spec. No "WIP" commits. No
  `--no-verify`.
- **Tech debt**: when review surfaces follow-ups, address them in the
  same PR. No parked TODOs.
- **Branch policy** (lumitra-studio repo): never develop on `main`.
  Always `feat/<short-description>` branches.
- **Infra**: Coolify on Hetzner for app hosting, Infisical for
  secrets, Cloudflare for DNS, Terraform for declarative setup where
  applicable.

## Stop conditions

Stop and ask Marlin before dispatch if:

- One of the architectural decisions above is unanswered.
- A spec's problem statement reveals a hidden dependency on
  something not in this list.
- The deploy reveals an Infisical project / Coolify configuration
  issue that needs Marlin's account access.
- Upstream provider (Vertex / KIE / Storage Brain) smoke test fails.
- You find yourself building tenant / ApiKey / quota / signup
  scaffolding. Stop: the v0.1 explicitly excludes those. If you
  think you need them, that's a sign to revisit the decision plan at
  `~/software-dev/ERP-suite/projects/lumitra-studio/docs/plans/2026-05-25-hosted-shape-decision.md`
  rather than build them speculatively.

## Report at the end

When all slices land (or you stop at a checkpoint):

1. Path(s) to specs written
2. PRs opened (numbers, branch names)
3. Coolify app URL + first successful end-to-end test (live service
   token, image generation, asset URL from Storage Brain)
4. Anything deferred and why
```

---

## Notes for Marlin (out-of-band, not part of the paste-in)

- Major scope reduction vs the previous 8-slice SaaS framing: this is
  now 2-3 slices. The decision plan at
  `~/software-dev/ERP-suite/projects/lumitra-studio/docs/plans/2026-05-25-hosted-shape-decision.md`
  captures why.
- The previous draft of this handover (`8 slices, SaaS v0.1`) is
  superseded. If you want it archived rather than overwritten, say so;
  otherwise the new shape is the canonical handover.
- Brand filesystem stays as-is. When a second tenant or contributor
  appears, revisit the brand-DB migration spec as a separate wave.
- The `LUMITRA_STUDIO_SERVICE_TOKEN` is rotation-capable: generate a
  new one in Infisical, redeploy, update consumer apps. Cheap because
  there's only one token and a handful of consumers. No revocation
  table needed at one-tenant scale.
- After deploy, the first consumer integration is lola-stories admin's
  marketplace cover-image generation (the original use case that
  triggered all this thinking). That's a separate spec in the
  lola-stories repo, not in this handover.
