---
task: mt-01
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
shared_state: [lockfile]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-01** (section "MT-01 - Subdomain generator" in `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`): a pure, tested function that produces a random, URL-safe, human-readable subdomain LABEL for publish-time allocation. This is a leaf building block with ZERO cross-deps. It must NOT touch Prisma, env, `server-only`, or any existing route.

## Read first

- The MT-01 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md` (the acceptance criteria are authoritative).
- `package.json` — `uuid@^13` is present, `nanoid` is ABSENT. You add `nanoid` as a direct dependency.
- An existing pure test for shape conventions, e.g. anything under `src/server/sites/__tests__/`.

## Definition of done

Create `src/server/sites/subdomain.ts`:
- `export function generateSubdomain(): string` — a lowercase DNS-label-safe slug. Either Framer-style `word-word-NNNNNN` OR a `customAlphabet` nanoid of length >= 8 over `[a-z0-9]` (internal hyphens allowed). Pick the `customAlphabet` nanoid approach unless you have a curated wordlist; it's simpler and collision-resistant. If you use a word-word form, embed the wordlists in this file (no network, no extra dep beyond nanoid).
- Output ALWAYS matches `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` (RFC-1035 label: <= 63 chars, no leading/trailing hyphen, lowercase).
- `export const RESERVED_SUBDOMAINS` (a `readonly` set/array) containing at minimum: `www`, `app`, `editor`, `api`, `admin`, `auth`, `mail`, `sites`. `export function isReserved(label: string): boolean` (case-insensitive). `generateSubdomain()` must NEVER return a reserved label (loop/regenerate if it does).
- PURE: no `import 'server-only'`, no Prisma, no `process.env`, no DB. Importable from a plain Vitest unit test with zero setup.

Create `src/server/sites/__tests__/subdomain.test.ts` (runs under the vitest `node` project automatically since it's under `src/server/**`):
- Generate >= 10000 labels; assert EVERY one matches the RFC-1035 regex AND `isReserved` is false for all.
- Assert `isReserved` is true for each reserved label (and case-insensitively, e.g. `'APP'`).
- A forced-collision demonstration: show that `generateSubdomain` itself does NOT dedupe across calls (dedup is the DB layer's job, asserted later in MT-06). E.g. assert that two calls can in principle collide / that the function has no internal registry — a comment + a test that the function is stateless is enough.

Add `nanoid` to dependencies: run `pnpm add nanoid` (this updates `package.json` AND `pnpm-lock.yaml`; commit both). Use a pinned recent version. Do NOT add it to devDependencies.

Plus the always-on gates:
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all pass.
- Single conventional commit, e.g. `feat(sites): pure RFC-1035 subdomain generator + reserved-label denylist (MT-01)`.

## Constraints

- Stay in this worktree. Do NOT modify any file other than `package.json`, `pnpm-lock.yaml`, the new `subdomain.ts`, and the new test.
- Do NOT wire this into the publish route, repository, or anything else — that is MT-06/MT-07's job. This spec is the pure function only.
- Do not push to any remote. When done, output a final message that the task is complete.

## Notes

- `nanoid` v5 is ESM-only; this repo is ESM/Next, so that's fine. If `customAlphabet` import shape causes a CJS/ESM issue under vitest, confirm the import works in the node test project before declaring done (the verify gate will catch it).
- Keep the label length comfortably under 63 (e.g. nanoid length 10-12) so that `<label>.sites.lumitra.co` stays well within DNS limits.
