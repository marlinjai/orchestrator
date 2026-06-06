---
task: auth-brain-deploy
spec: docs/superpowers/plans/2026-06-06-auth-brain-deploy.md
shared_state: [lockfile, next-config, claude-md]
marlin_proxy: shadow
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  irreversible_ops: escalate
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
---

# Goal

Prepare auth-brain for its first production deployment at `https://auth.lumitra.co`. This task covers the **code changes only** (Steps 6 and 8 of the deployment plan at `docs/superpowers/plans/2026-06-06-auth-brain-deploy.md`): the Infisical-based runtime entrypoint, Dockerfile wiring, `/api/health` endpoint, and the Coolify deploy GitHub Actions workflow. You are working on top of `feat/auth-brain-v1` (which has all v1 implementation code). Do NOT touch infrastructure (Terraform, Coolify, secrets, DNS) -- those are irreversible_ops that Marlin runs after this PR merges.

## Read first

- `docs/superpowers/plans/2026-06-06-auth-brain-deploy.md` -- the full deployment plan. Steps 6 and 8 are your scope. Read Steps 1-5 and 7 for context on what the runtime expects.
- `packages/app/Dockerfile` -- the existing Dockerfile you will extend with the entrypoint and health route.
- `.github/workflows/ci.yml` -- the existing CI workflow. Your deploy workflow follows a similar structure but uses aarch64 runners, Docker buildx, and Coolify webhook dispatch.
- `packages/app/src/app/api/sessions/verify/route.ts` -- confirms the pattern for Next.js route files in this app. Your `/api/health` follows the same shape.
- Root `package.json` -- note the `infisical run` pattern in dev scripts. The entrypoint mirrors this for production.

## Definition of done

1. **`packages/app/entrypoint.sh`** exists, is executable (`chmod +x`), and does exactly:
   - Fetches an Infisical machine-identity token via universal-auth using `INFISICAL_UNIVERSAL_AUTH_CLIENT_ID` and `INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET` env vars (both injected by Coolify at runtime, not baked in).
   - Calls `infisical run --token="$TOKEN" --projectId="$INFISICAL_PROJECT_ID" --env=prod --domain=https://infisical.lumitra.co -- "$@"` so the CMD receives fully injected secrets.
   - Uses `set -e` and `exec` (not `sh -c`). No hardcoded values, no default env fallbacks that mask a missing secret.

2. **`packages/app/Dockerfile`** updated so the runner stage:
   - Installs `curl` (for Infisical CLI bootstrap in the entrypoint) via `apk add --no-cache curl` before any app copy.
   - Copies `entrypoint.sh` to `/entrypoint.sh` and `chmod +x`.
   - Sets `ENTRYPOINT ["/entrypoint.sh"]`.
   - CMD runs migrations then starts: `CMD ["sh", "-c", "pnpm --filter @auth-brain/app db:migrate && pnpm --filter @auth-brain/app start"]`.
   - The build and deps stages are UNCHANGED.

3. **`packages/app/src/app/api/health/route.ts`** exists:
   ```typescript
   import { NextResponse } from 'next/server';
   export const dynamic = 'force-dynamic';
   export function GET() {
     return NextResponse.json({ ok: true });
   }
   ```
   No auth, no DB, just `{ ok: true }`. This is the Coolify health check target.

4. **`.github/workflows/deploy.yml`** exists and:
   - Triggers on `push: branches: [main]` only (no PR trigger).
   - Uses `runs-on: ubuntu-24.04-arm` (the shared Hetzner server is aarch64).
   - Sets up Docker buildx with `platform: linux/arm64`.
   - Builds the image from `packages/app/Dockerfile` (context: repo root) and pushes to the registry Coolify watches (use the `COOLIFY_WEBHOOK` + `COOLIFY_TOKEN` secrets pattern -- see Step 8 of the plan for exact secrets list).
   - After build: sends a Coolify deploy webhook via `curl -X POST` using `secrets.COOLIFY_WEBHOOK` with `Authorization: Bearer ${{ secrets.COOLIFY_TOKEN }}`.
   - Sets these GitHub secrets as requirements in a comment at the top of the workflow file (never hardcode values):
     `COOLIFY_WEBHOOK`, `COOLIFY_TOKEN`, `INFISICAL_UNIVERSAL_AUTH_CLIENT_ID`, `INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET`.
   - No `NEXT_PUBLIC_*` build args needed (auth-brain has no public env vars baked at build time; all secrets come from Infisical at runtime via the entrypoint).
   - Health check step: `curl --retry 10 --retry-delay 10 --fail https://auth.lumitra.co/api/health` after deploy webhook fires.

5. **No migration** is generated or applied. auth-brain v1 does not add schema changes on top of what is already in `feat/auth-brain-v1`. If you discover that the Dockerfile's CMD references a `db:migrate` script that does not exist, record an `open_thread` and skip that CMD fragment (do not invent a migrate script).

6. **`packages/app/entrypoint.sh`** must install the Infisical CLI if it is absent in the alpine image. Use the official alpine install path from the deployment plan (Step 6):
   ```sh
   curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.alpine.sh' | sh
   apk add --no-cache infisical
   ```
   This runs inside the container at boot, not at image build time (keeps the image layer clean).

7. Typecheck and lint pass on the changed files: `pnpm typecheck && pnpm lint`. Do NOT run the full integration test suite -- the local postgres on port 5432 is occupied by another project and the integration tests cannot connect.

8. Spec plan `status` stays `decided`. Do not flip it.

9. Single commit on this worktree branch. Conventional commit message describing WHY (production deploy of auth-brain requires a runtime secret-injection entrypoint, health endpoint, and Coolify CI/CD workflow).

10. Final `update_state(kind="decision")` entry summarizing: what was built, what three env vars Coolify must inject (`INFISICAL_UNIVERSAL_AUTH_CLIENT_ID`, `INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET`, `INFISICAL_PROJECT_ID`), and what GitHub secrets must be set before the workflow fires. This is the handover note to Marlin for the infrastructure steps.

## Constraints (hard)

- **Do NOT deploy, do NOT apply Terraform, do NOT create Coolify services, do NOT set any real secrets, do NOT push OpenFGA schema, do NOT run the analytics migration.** Those are Steps 1-5, 7, 9-10 of the deployment plan. Marlin runs them after this PR merges.
- Stay in this worktree. Do not modify files outside it. Do not push to any remote.
- Do not generate or log any actual secret values. The entrypoint reads them from env at container boot time; you only write the script structure.
- No em-dashes or en-dashes in any output, code, comments, or commit message.
- Report `file_touched` for each file created/modified. Report `decision` for any non-obvious call. If `db:migrate` script is missing, file `open_thread` instead of inventing it.
- If the Dockerfile CMD for migrations turns out to need a separate investigation, scope it as an `open_thread` and ship the rest.

## Notes

- The `packages/app/src/app/api/auth/` directory already exists (it is part of the auth-brain v1 implementation). Your health route goes under `packages/app/src/app/api/health/route.ts` -- a sibling, not inside `auth/`.
- The `deploy.yml` Coolify webhook pattern: after the image is pushed, Coolify auto-detects the new image and redeploys IF the application is configured with a webhook trigger. The exact webhook URL comes from the Coolify UI (Marlin will wire it after service creation in Step 5). Use `${{ secrets.COOLIFY_WEBHOOK }}` as a placeholder -- it is conventional and the CI step will simply no-op if the secret is not yet set.
- The outbox worker uses the same Dockerfile but a different CMD override set in Coolify, not in CI. You do NOT need a separate Dockerfile or a separate build job for the worker.
- `db:migrate` in the CMD is a pnpm script the app must define. Check `packages/app/package.json` -- if it exists, use it. If it does not, file `open_thread` and use just the start command in CMD.
