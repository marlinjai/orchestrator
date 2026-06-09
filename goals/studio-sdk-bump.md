---
task: studio-sdk-bump
verify: pnpm install --no-frozen-lockfile && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Bump `@marlinjai/storage-brain-sdk` to `^0.9.0` in the one remaining package that still pins the old range, so the whole lumitra-studio monorepo is on a single SDK version (the root `package.json` is already `^0.9.0`).

## The change (small and exact)

- `packages/lumitra-core/package.json` currently pins `"@marlinjai/storage-brain-sdk": "^0.8.0"` (line ~53). Change it to `"^0.9.0"` to match the root.
- Run `pnpm install` to update the lockfile to the resolved 0.9.x.
- That is the entire intended change. Do NOT bump any other dependency.

## Read first

- `package.json` (root, already `^0.9.0` for reference) and `packages/lumitra-core/package.json`.
- The package's own source that imports from `@marlinjai/storage-brain-sdk`, to confirm no API broke between 0.8 and 0.9 (fix any type breakage that the bump surfaces, in this package only).

## Definition of done

- `packages/lumitra-core/package.json` pins `@marlinjai/storage-brain-sdk` at `^0.9.0`.
- `pnpm install --no-frozen-lockfile` resolves cleanly and the lockfile is updated + committed.
- `pnpm test` passes (the repo's vitest suite; it is wrapped in `infisical run` for env, that is expected).
- Single conventional-commit on this branch.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Bump ONLY `@marlinjai/storage-brain-sdk` in `packages/lumitra-core`. Do not touch other deps, do not run `pnpm update` broadly, do not regenerate unrelated lockfile entries.
- KNOWN ADVISORY (not a failure): a `unmet peer zod@^3` warning may appear because the published `@marlinjai/brain-core@0.1.0` (a transitive peer via the SDK) declares `zod ^3` while studio runs zod 4. This is pre-existing and tracked separately (`zod4-republish-cascade`). It is a warning, NOT a regression: do not try to fix it here, do not pin or downgrade zod, do not touch brain-core.
- Do not push to any remote. When done, output a final completion message.

## Notes

- If `pnpm test` cannot reach Infisical (token/network) in the worktree, say so clearly in an `open_thread` and stop rather than working around the env: that is an operator-side issue, not a code fix.
