---
task: coolify-deploy
spec: docs/specs/2026-05-25-coolify-deploy.md
---

# Goal

Implement slice 3 (final) of the Lumitra Studio internal-infra deploy v0.1: produce the CODE ARTIFACTS needed to deploy to Coolify/Hetzner. This Worker does NOT provision Coolify, Infisical, DNS, or Storage Brain (those are operator-driven post-merge, per the spec's "out-of-band notes"). Single conventional commit on the existing `feat/coolify-deploy` branch in this worktree.

## Read first

- The spec at `docs/specs/2026-05-25-coolify-deploy.md` (full contents). Pay particular attention to the "Sequence within the slice" section: steps 1, 2, 3, 9, 10, 11 are yours. Steps 4 to 8 are operator/Marlin and must NOT be attempted by you.
- The hosted-shape decision at `docs/plans/2026-05-25-hosted-shape-decision.md`
- The slice 1 lib package: `packages/lumitra-core/src/storage.ts` (the env-var rename target)
- `package.json` (scripts, deps, `packageManager` field, Next 16.2.1)
- `next.config.ts` (currently has `turbopack.root`)
- `prisma/schema.prisma` and `prisma/migrations/` (Dockerfile must run `prisma migrate deploy` not `migrate dev`)
- Any existing `.github/workflows/` (to follow the repo's GHA conventions if one exists)
- `CLAUDE.md` if present
- The lola-stories API GHA workflow pattern (referenced in the spec; you can look at this repo's own existing workflows if any, or follow the spec's contract directly)

## Definition of done

CODE ARTIFACTS only (operator-driven provisioning is excluded; see Out-of-scope below):

### Code changes

1. **`next.config.ts`**: add `output: 'standalone'`. Keep `turbopack.root`. Verify `pnpm build` (under `infisical run`) emits `.next/standalone/server.js`.

2. **`Dockerfile`** at repo root, multi-stage per the spec:
   - Stage 1 (`deps`): `node:20-bookworm-slim` base, corepack-activated pnpm at the pinned version from `package.json`'s `packageManager` field, copy lockfile + workspace manifests + `packages/*/package.json`, `pnpm install --frozen-lockfile`.
   - Stage 2 (`builder`): same base, copy deps from stage 1, copy source, `pnpm --filter @marlinjai/lumitra-core build`, `pnpm prisma generate`, `pnpm build`.
   - Stage 3 (`runtime`): `node:20-bookworm-slim`, install Infisical CLI via the official install script pinned to the version lola-stories API uses (look it up in lola-stories' Dockerfile if accessible, else use latest stable pinned by SHA or version), install sharp's `libvips` system dep if missing, copy `.next/standalone`, `.next/static`, `public/`, `brands/`, `prisma/` (schema + migrations), `node_modules/.prisma`, the entrypoint script. `WORKDIR /app`, `EXPOSE 3000`, `USER node` (non-root), `ENTRYPOINT ["./entrypoint.sh"]`.
   - Do NOT declare a `HEALTHCHECK` directive in the Dockerfile (gotcha from `reference_coolify_storage_brain_deploy_gotchas.md`; Coolify configures healthcheck at the proxy layer).

3. **`entrypoint.sh`** at repo root, chmod +x, executable:
   - shebang `#!/usr/bin/env sh`, `set -e`
   - If `GOOGLE_APPLICATION_CREDENTIALS_JSON` is set: write to `$(mktemp -t gcp-creds.XXXXXX.json)`, export `GOOGLE_APPLICATION_CREDENTIALS=<path>`.
   - Run `infisical run --domain https://infisical.lumitra.co -- pnpm prisma migrate deploy` (fail container start on bad migration).
   - `exec infisical run --domain https://infisical.lumitra.co -- node server.js` (Next.js standalone entry).

4. **`.dockerignore`**: standard Node + Next exclusions plus `brands/*/private/` if such a pattern exists, `*.test.ts`, `*.spec.ts`, `docs/`, `node_modules`, `.next`, `coverage`, `.env*`, `.infisical.json`, `prisma/migrations/.snapshot.sql` if present.

5. **`.github/workflows/deploy.yml`**: triggered on `push` to `main`. Two jobs:
   - `build-and-push`: checkout, docker buildx, login to GHCR using `GITHUB_TOKEN`, `docker build` and push to `ghcr.io/marlinjai/lumitra-studio:latest` and `:${{ github.sha }}`. Builds on `ubuntu-latest` (NOT a macOS runner) because sharp must be x86_64 to match Hetzner.
   - `deploy` (`needs: [build-and-push]`): `curl -fsSL -X GET "$COOLIFY_DEPLOY_WEBHOOK"` (URL from repo secret `COOLIFY_DEPLOY_WEBHOOK`).
   - Pass `LUMITRA_STUDIO_COMMIT_SHA=${{ github.sha }}` as a Docker build arg so the health route can surface it. The Dockerfile must accept this `ARG` and `ENV` it into the runtime stage.

6. **`scripts/smoke-deploy.ts`**: runnable via `pnpm exec tsx scripts/smoke-deploy.ts` from a laptop with Infisical access. Targets `studio.lumitra.co` (override via `--base-url` CLI flag for local testing). Reads `LUMITRA_STUDIO_SERVICE_TOKEN` from process env. Asserts:
   - `GET /api/health` returns HTTP 200 with `{status:'ok', db:'ok', queue:'ok'}` (version field present, value not asserted).
   - `POST /api/generate` (with a small brand-prompt payload appropriate to one of the existing brands; pick the smallest viable one by scanning `brands/*/brand.json`) returns 200 / 202 with a job id. Poll the resulting job (presumably via an existing `/api/jobs/:id` or `/api/v1/jobs/:jobId` route; verify against `src/app/api/v1/jobs/`) until status is `succeeded` or `failed` or a 90s timeout.
   - On success: confirm the resulting asset URL resolves with HTTP 200 (HEAD request).
   - Connect to `LUMITRA_STUDIO_DATABASE_URL` and assert the corresponding `Job` row has a non-null `costUsd` (verifies billing pipeline). Use Prisma client.
   - Exit 0 on full success, non-zero with a structured diagnostic on any failure. Print PASS / FAIL per check.

7. **`docs/internal/deploy-runbook.md`**: full operator runbook covering everything the Worker does NOT do (see Out-of-scope below). Lay it out so an operator (Marlin or me) can follow it cold:
   - Pre-reqs (Coolify access, Infisical access, Cloudflare access, GHCR PAT, Storage Brain admin token)
   - Step 1: Provision Coolify Postgres (database name `lumitra_studio`, daily backups enabled, capture connection string)
   - Step 2: Create Infisical project `lumitra-studio` and load secrets (full list per the spec)
   - Step 3: Provision Storage Brain tenant `lumitra-studio` (allowedFileTypes: null, follow `reference_storage_brain_admin_via_agent.md` pattern)
   - Step 4: Create Cloudflare DNS A or CNAME for `studio.lumitra.co` (proxy off for LE)
   - Step 5: Create Coolify project + app (image source: GHCR `ghcr.io/marlinjai/lumitra-studio:latest`, domain: studio.lumitra.co, healthcheck: HTTP GET /api/health on port 3000)
   - Step 6: Add `COOLIFY_DEPLOY_WEBHOOK` to GitHub repo secrets
   - Step 7: First deploy via `git push origin main` (or empty commit if main already current), watch Coolify log
   - Step 8: Run `pnpm exec tsx scripts/smoke-deploy.ts`
   - Rotation procedure (edit Infisical secret + redeploy + verify)
   - Rollback procedure (Coolify "Redeploy previous" + verify health)

8. **Env var rename** in `packages/lumitra-core/src/storage.ts`: change `process.env.STORAGE_BRAIN_API_KEY` to `process.env.LUMITRA_STUDIO_STORAGE_BRAIN_API_KEY` and `process.env.STORAGE_BRAIN_ENDPOINT` to `process.env.LUMITRA_STUDIO_STORAGE_BRAIN_ENDPOINT` (carryover from slice 1 review; the Infisical secret list in the spec uses the namespaced names). Update any other references via `git grep STORAGE_BRAIN_API_KEY` and `git grep STORAGE_BRAIN_ENDPOINT`. Update the runbook to mention "if local dev was running against legacy var names, add the new ones via `infisical secrets set`."

### Verification

- `pnpm exec tsc --noEmit` clean across the workspace
- `pnpm --filter @marlinjai/lumitra-core build` still succeeds (env-var rename doesn't break types)
- `pnpm --filter @marlinjai/lumitra-core test` still 99/99 passing
- `infisical run --domain https://infisical.lumitra.co -- pnpm build` succeeds (Next.js standalone build green; this requires Infisical to have an env). If you cannot run `infisical run` (CLI not in the worktree environment OR no laptop login), document why and run `DATABASE_URL=postgres://stub:stub@localhost:5432/stub pnpm build` as a no-op fallback that at least exercises the compile / collect-page-data steps.
- `docker build .` succeeds locally (the orchestrator host should have Docker). Inspect the resulting image: confirm non-root user, image size, no `.env*` baked in.
- Spec frontmatter `status: draft` becomes `status: in-progress` then `status: completed`.
- Single conventional commit: `feat(deploy): Dockerfile, GitHub Actions, smoke test, runbook (slice 3)`. Body summarizes the artifact list and explicitly notes that Coolify / Infisical / DNS provisioning is operator-driven post-merge.

## Out of scope (operator-driven, do NOT attempt)

These steps need Marlin's Coolify and Infisical accounts AND/OR live infra access. Escalate BEFORE attempting any of them:

- Creating a Coolify project, application, or Postgres instance
- Creating an Infisical project or loading secrets into one
- Provisioning a Storage Brain tenant
- Creating a Cloudflare DNS record
- Adding a GitHub repo secret (`COOLIFY_DEPLOY_WEBHOOK`)
- Generating the bearer token via `openssl rand -base64 48` (the operator does this and stores it directly into Infisical)
- Running the smoke test against the deployed instance (no deployed instance exists yet)
- Triggering the first deploy
- ANY interaction with live infra (Coolify UI, Hetzner panel, Vertex AI service-account JSON download)

You produce the artifacts and the runbook. The operator follows the runbook.

## Constraints

- **Stay in this worktree.** Path is `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-studio-orch-coolify-deploy`. Do not modify files anywhere else.
- **Do not push to any remote.** No `git push`.
- **Do not touch the database.** No `prisma migrate dev`. (The Dockerfile contains `prisma migrate deploy` for runtime use; that is configuration, not execution.)
- **Do not introduce features outside the spec's "In scope".** No Terraform-for-Coolify in v0.1 (the spec says runbook now, Terraform later). No CDN. No multi-region. No staging environment. No custom monitoring beyond Coolify's built-in healthcheck. No rate limiting. No CORS.
- **Naming**: `LUMITRA_STUDIO_*` for all new env vars and the rename target in `storage.ts`. Never bare `LUMITRA_*` or legacy `STORAGE_BRAIN_*` in NEW code.
- **Typography**: no em-dash `—` or en-dash `–` anywhere (Dockerfile comments, runbook prose, commit message, GHA YAML comments, spec status update, script messages). Use colons, parentheses, commas, periods.
- **No `--no-verify`**, no force operations, no `git push` of any kind.
- **Conventional commit only**, single commit, no WIP commits, no follow-up cleanup commits.

## Escalation triggers

Stop and escalate (via `update_state` with `kind="escalation"`) if:

- The Dockerfile or entrypoint depends on infra you cannot inspect (e.g. unsure whether sharp needs system deps on the chosen base image; if uncertain, install `libvips` and document)
- Storage Brain SDK does not work with the renamed env vars (look at the SDK constructor; the env var name is just a host-side convention, the SDK itself takes args)
- The smoke test cannot infer a valid brand slug or generate payload from the existing brands directory
- Prisma `migrate deploy` fails on the existing migrations (run it dry under `prisma migrate status` if you have an Infisical-injected DATABASE_URL; if you cannot reach the dev DB, escalate)
- `pnpm build` under `output: 'standalone'` fails for a non-obvious reason (e.g. Turbopack incompatibility; surface the error)
- The env var rename has cross-package callers you cannot reach without expanding scope dramatically (escalate before mass-renaming)
- You find yourself wanting to do any of the out-of-scope items (provision Coolify, edit Infisical, create DNS records, add GH secrets): stop

## Notes

- Worktree base branch: `main` (slices 1 and 2 already landed). Branch is `feat/coolify-deploy` already created off main.
- Infisical CLI on the host: `infisical --version` should work; if not, document in the runbook (operator installs).
- The runbook is the most-important deliverable in this slice. It is the artifact Marlin will follow to actually go live. Make it cold-readable: every step numbered, every command literal (or the exact UI navigation if no CLI option), every value placeholder explicit (e.g. `<HETZNER_SERVER_IP>` not "your IP").
- After this slice lands and the operator follows the runbook, Lumitra Studio is live at studio.lumitra.co. The next deliverable (lola-stories admin integration) is a separate spec in a separate repo, NOT in this slice.
- Final message at the end of the run: confirm the branch name, the commit SHA, the artifact list (Dockerfile, .dockerignore, entrypoint.sh, .github/workflows/deploy.yml, scripts/smoke-deploy.ts, docs/internal/deploy-runbook.md, next.config.ts edit, packages/lumitra-core/src/storage.ts edit, spec status flip), and any open_thread entries.
