---
task: lumitra-studio-brand-db-migration
spec: docs/specs/2026-06-01-brand-db-migration.md
depends_on: [lumitra-studio-auth-brain]
shared_state: [prisma, migrations]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement the **brand DB migration** per the spec at `docs/specs/2026-06-01-brand-db-migration.md`: move brand kits from the filesystem (`brands/<slug>/`) into Postgres, with reference images in Storage Brain, so brands are durable on the hosted Studio and can be created and have references uploaded through the UI. Include a one-time, idempotent migration of the existing `lola-stories` brand. The acceptance bar: brands and references resolve from Postgres + Storage Brain, a brand created via the API survives a redeploy, and prompt assembly output is unchanged versus the filesystem loader.

## Read first

- The spec in full: `docs/specs/2026-06-01-brand-db-migration.md`.
- `prisma/schema.prisma` (you add `Brand` + `BrandReference`, relate `Project.brandSlug`; do NOT break existing rows).
- The current filesystem brand system: `brands/lola-stories/` (brand.json, context.md, library.json, references/*), the brand loader in `@marlinjai/lumitra-core/brand` (`loadBrand(brandRootDir, slug) -> BrandContext`), and `buildBrandPrompt` (must stay unchanged: keep the `BrandContext` shape identical).
- The brand API routes: `src/app/api/brands/route.ts` and the `:slug` subroutes (context, library, library/upload). The UI already calls these (`src/app/page.tsx`, `src/components/BrandPanel.tsx`).
- Storage Brain usage for binaries and URL signing: `src/lib/asset/sign.ts`, `src/lib/storage/*` (reuse the existing SDK/util; do not invent a new client).
- The repo `CLAUDE.md` and existing test patterns.

## Definition of done

1. Prisma `Brand` and `BrandReference` models per the spec; relate `Project.brandSlug`. A new migration under `prisma/migrations/`, generated with `prisma migrate dev --create-only` against a LOCAL throwaway DB, committed but NOT applied to prod.
2. A DB-backed brand loader producing the SAME `BrandContext` the filesystem loader returns (so `buildBrandPrompt` and the generation pipeline are unchanged). Keep the filesystem loader available behind a flag/fallback for now (do not delete the `brands/` tree in this slice).
3. Brand API routes refactored to DB: `GET`/`POST /api/brands`, `PATCH /api/brands/:slug`, `:slug/context`, `:slug/library`, and `:slug/library/upload` (upload to Storage Brain, create a `BrandReference` row, return a signed URL).
4. One-time idempotent migration script `src/scripts/migrate-brands-to-db.ts` wired as `pnpm migrate:brands`: read `brands/<slug>/`, upsert `Brand` + `BrandReference` rows, upload reference binaries to Storage Brain, skip already-imported references. Designed to be run by a human against prod; safe to re-run.
5. Tests: brand CRUD against a test DB; the DB loader's `BrandContext` for lola-stories matches the filesystem loader (golden compare); upload creates a Storage Brain file + a row; prompt assembly output unchanged for a fixture brand.
6. `pnpm test`, `pnpm lint`, typecheck pass. (Bare-build env failures from missing `DATABASE_URL` are the known `infisical run -- pnpm build` pattern, not a regression.)
7. Spec frontmatter `status` stays `decided`.
8. Single commit, conventional message describing the WHY (filesystem brands are ephemeral on the host; move them to durable Postgres + Storage Brain so cofounders can self-serve brand kits).

## Constraints (hard, do not violate)

- **Do NOT apply the migration to any non-local database. Do NOT run `pnpm migrate:brands` against prod. Do NOT deploy. Do NOT touch production secrets.** Those are Marlin's steps (irreversible_ops). Generate the migration with `--create-only` against a local throwaway DB, write the import script, and STOP.
- Do NOT change the `BrandContext` shape or the prompt-assembly logic. If a change there seems necessary, that is a `scope_change`: escalate.
- Do NOT delete the `brands/` filesystem tree or remove the filesystem loader in this slice (keep rollback trivial until prod is verified). Note the cleanup as an `open_thread`.
- Stay in this worktree. Do NOT push to any remote. No destructive git/shell commands.
- No em-dashes or en-dashes anywhere (repo style rule). Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (e.g. the `BrandReference` category model, the Project relation choice), `open_thread` (filesystem-tree cleanup, per-tenant isolation), `commit`.

## Notes

- This slice serializes after `lumitra-studio-auth-brain` (both touch `prisma` + `migrations`; the dispatcher will not run them concurrently). Recommended order is auth first.
- Storage Brain must be reachable from the eventual deploy (it already is, for generated assets). Reuse the existing SDK and the existing URL-signing path; do not add a second storage client.
- Out of scope (note as `open_thread` if relevant): per-tenant brand ownership, brand versioning, folding brands into the unified Asset table.
