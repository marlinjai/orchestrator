---
task: lumitra-studio-fal-image-provider
spec: docs/specs/2026-06-04-fal-image-provider.md
shared_state: [lockfile, env]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement **fal.ai as the image-generation provider** for Lumitra Studio per the spec at `docs/specs/2026-06-04-fal-image-provider.md`: add a `fal` provider to the existing abstraction (parallel to `kie.ts` / `vertex.ts`), add fal image models to the catalog, make a fal model the image default, and route fal jobs through the existing job/cost/storage flow. Keep Vertex as the fallback; do not touch KIE. The acceptance bar: `getProvider('fal').generateImage(...)` works end to end against a mocked fal client, the catalog defaults to a fal image model, and the existing image flow generates via fal with cost recorded, with zero live fal spend during the run.

## Read first

- **AUTHORITATIVE fal API reference, read BEFORE writing any fal code: `docs/internal/research/fal-api-reference.md`** (dual-sourced; confirmed model ids, schemas, the `Authorization: Key` header, `subscribe` returning `{ data, requestId }`, `fal.storage.upload`, the `image_url` vs `image_urls` split, and the compute-the-cost rule). It resolves every hedge below.
- The spec in full: `docs/specs/2026-06-04-fal-image-provider.md`.
- The provider contract: `packages/lumitra-core/src/providers/types.ts` (`ProviderId`, `ProviderClient`, `GenerateImageInput`, `GenerateImageResult`, `NotImplementedError`).
- The mirror: `packages/lumitra-core/src/providers/kie.ts` (async submit -> poll -> fetch result URL -> base64 data URL -> `{ images, costUsd }`) and its tests `kie.spec.ts` / `kie.test.ts`.
- The registry: `packages/lumitra-core/src/providers/index.ts` (`getProvider`, the `Record<ProviderId, ProviderClient>`).
- The catalog: `packages/lumitra-core/src/models/catalog.ts` (`MODEL_CATALOG`, `ModelEntry`, `isDefault`, the image entries' `cost` shape) and how `getProviderModelName` maps a catalog id to an upstream model name.
- The handler (provider-agnostic, should need no change beyond routing): `src/lib/jobs/handlers/generate-image.ts`.
- `@fal-ai/client` usage: read its README/types in `node_modules/@fal-ai/client` after install rather than guessing the `subscribe` / `queue` surface. Auth is `Authorization: Key ${FAL_KEY}` for REST or `fal.config({ credentials })` for the client.
- The repo `CLAUDE.md` and the existing vitest patterns.

## Definition of done

Per the spec's Scope and Acceptance:

1. `@fal-ai/client` added (lockfile).
2. `packages/lumitra-core/src/providers/fal.ts` exporting `falProvider: ProviderClient`: real `generateImage` (map `GenerateImageInput` to fal FLUX inputs, convert returned CDN URLs to base64 data URLs mirroring `kie.ts`, populate `costUsd` from fal pricing), and `generate3D` / `remesh3D` / `texture3D` throwing `NotImplementedError('fal', ...)`. Read `FAL_KEY` at CALL time, never at module load. Brand reference images arrive as `inputImages` and MUST be mapped PER MODEL (see the spec's 'Brand reference images: per-model capability' section): Nano Banana edit endpoint takes an `image_urls` array (full brand refs), Kontext takes one `image_url`, FLUX 1.1/schnell take none (drop with a returned warning plus a logged `decision`, never silently).
3. `ProviderId` widened to include `'fal'` in `providers/types.ts`; `fal: falProvider` registered in `providers/index.ts`.
4. Catalog entries for fal image models (`fal-ai/nano-banana-2`, FLUX 1.1 [pro], FLUX.1 [schnell], FLUX.1 Kontext [pro] for edits) using the existing image-entry `cost` shape (USD, not `{ credits }`); set the image `isDefault` to `fal-ai/nano-banana-2` (same model as today's KIE default) and remove `isDefault` from the KIE `nano-banana-2` entry; add the catalog-id -> upstream-fal-model-name mapping where `getProviderModelName` resolves it. Exact ids/schemas/prices: `docs/internal/research/fal-api-reference.md`. Extend `ModelCapabilities` with `maxInputImages?: number` and set it per entry (0 for flux-pro/v1.1 and flux/schnell, 1 for flux-pro/kontext, 8 for Nano Banana edit models). Adopt the Weave-style task classification (option a, one task per entry) per the spec's 'Model taxonomy' table: extend `Modality` with `video` and `ModelTask` with `image-edit` / `text-to-video` / `image-to-video` (video enum values only, no video models); classify nano-banana-2 = text-to-image (default), nano-banana-2/edit = image-to-image AND image-edit, flux-pro/v1.1 and flux/schnell = text-to-image, flux-pro/kontext = image-edit. UI picker regroup is OUT of scope (follow-up).
5. Tests mirroring `kie.spec.ts`: mocked fal client / fetch; assert request shape (model mapping, `Key` auth, params), response mapping (URL -> data URL, costUsd), `NotImplementedError` on 3D methods, catalog validity (exactly one image default, fal entries well-formed), handler routes `provider: 'fal'`. NO live fal calls.
6. `pnpm test` (full suite; the local DB is available this run), `pnpm lint`, and typecheck pass.
7. Spec frontmatter stays `decided`. Single commit, conventional message describing the WHY (make the decided fal backbone real for image gen; default flips off KIE to fal).

## Constraints (hard, do not violate)

- **Do NOT make any live fal API call.** It costs money and needs `FAL_KEY`, which you do not have. Every test mocks the fal client / `fetch`. Live verification is a human step after deploy.
- **Do NOT add `FAL_KEY` to Infisical, do NOT deploy, do NOT touch production secrets.** Marlin does those (irreversible_ops).
- Do NOT remove or change the Vertex or KIE providers (Vertex stays the fallback; KIE stays for the future MJ/Suno adapter). You only flip the catalog DEFAULT off KIE onto fal.
- Do NOT implement fal 3D / video / audio here (out of scope; the 3D methods throw `NotImplementedError`). Note them as `open_thread`.
- Stay in this worktree. Do NOT push to any remote. No destructive git/shell commands.
- No em-dashes or en-dashes anywhere (repo style rule). Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (e.g. subscribe vs queue-poll, the cost computation, the edit/image-to-image path), `open_thread` (3D/video/audio follow-ons), `commit`.
- The image default-model flip is a `product_decision`: implement the recommended default (`fal-ai/nano-banana-2`) but flag it in your final report so Marlin can confirm or change the UI default. If the spec leaves a real fork unanswered, make the call that mirrors `kie.ts` and record it as a `decision`; do not stall.

## Notes

- Exact `@fal-ai/client` model ids, input/output schemas, the `image_url` (Kontext, single string) vs `image_urls` (Nano Banana edits, array) split, and per-model pricing are ALL in `docs/internal/research/fal-api-reference.md`. Use them verbatim; its `Verify at build time` checklist lists the few items to confirm against the installed client (npm version, nano-banana-2 t2i fields).
- This slice is parallel-safe with the brand-DB slice (no shared Prisma/migrations state); it shares only `lockfile` and `env` with other dependency-adding slices.
- Storage Brain persistence and brand-aware prompt assembly are upstream of the provider and need no change: the provider just returns base64 data URLs + cost like `kie.ts`.
