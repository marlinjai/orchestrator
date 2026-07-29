---
task: abc-pubcookie-keyid
verify: pnpm --filter @marlinjai/analytics-core build && pnpm --filter @marlinjai/analytics-react build && pnpm --filter @marlinjai/analytics-tracker build && pnpm typecheck && pnpm test -- --run && bash scripts/check-bundle-size.sh
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Close the one tracked follow-up from the WS-A/WS-A.2 work: the server-set public variant cookie (`lumitra_variants_pub`) currently carries experiment KEYS mapped to variant keys, but NOT experiment IDs. So the browser tracker's first event fired in its constructor (the initial session_start / pageview) cannot be tagged with `experimentId` until the async remote-config fetch loads the key to id map. Fix it by shipping a key to id map in the public cookie so the tracker can tag `experimentId` + `variant` on events immediately, before remote config arrives.

## Read first

- `packages/core/src/variants.ts` (the cookie contract: `encodeVariantsPublic` / `decodeVariantsPublic`, cookie name constants, the encoded shape). This is where the public mirror is produced and parsed.
- `packages/react/src/middleware.ts` (where the middleware calls `assignAll` and writes the `lumitra_variants_pub` cookie; you must pass experiment IDs into the public encode).
- `packages/tracker/src/server-variants.ts` (the tracker's inline decode of the public cookie) and `packages/tracker/src/experiment.ts` (`getActiveExperiments()` maps experiment-key to experiment-id from `this.experiments`, which is empty pre-config; this is the gap) and `packages/tracker/src/tracker.ts` (constructor order: hydrate then `track()`).
- The existing tests: `packages/core/src/__tests__/variants.test.ts`, `packages/tracker/src/__tests__/{server-variants,tracker-hydration}.test.ts`.

## What to change

1. Extend the PUBLIC cookie payload (`encodeVariantsPublic` in core) to include each running experiment's `id` alongside its `key` and assigned `variant` (e.g. an array of `{key, id, variant}` or a parallel key->id map). Keep it backward-tolerant: a cookie without ids must still decode (treat id as optional). Do NOT change the SIGNED cookie contract.
2. Pass the experiment IDs through in `packages/react/src/middleware.ts` when it encodes the public cookie (the running experiments it fetches already carry ids).
3. In the tracker, decode the ids and make `getActiveExperiments()` (or the hydration path) able to return `experimentId` for hydrated experiments BEFORE remote config loads, so the first constructor-fired event is tagged with both `experimentId` and `variant`.
4. Tests: a constructor-fired event is tagged with `experimentId`+`variant` when the public cookie carries ids; a cookie WITHOUT ids still decodes and degrades exactly as today (no crash, variant still known); parity (decoded variant === `assign()`); signed-cookie path unchanged.

## Definition of done

- The `verify` gate passes (builds + typecheck + full test run + bundle-size check).
- `git push -u origin orchestrator/abc-pubcookie-keyid` then open a PR: `gh pr create --base main --title "feat(analytics): ship experiment key to id map in the public variant cookie" --body "<what/why/how-verified>. Closes the WS-A.2 first-pageview id-tagging follow-up."`. NO em-dashes/en-dashes anywhere. End the PR body with a blank line then: 🤖 Generated with [Claude Code](https://claude.com/claude-code)
- Single (or few) conventional-commit(s) on this branch describing the why.

## Constraints (hard, this is an unattended overnight run)

- BUNDLE BUDGET IS TIGHT: the tracker is only ~45 bytes under the 6KB gzip cap. Your change MUST keep `bash scripts/check-bundle-size.sh` green. Parse the cookie inline, add zero runtime deps, trim if needed. If you genuinely cannot fit it under 6KB, do NOT raise the budget (that is Marlin's policy call): ESCALATE instead.
- NEVER merge to main. NEVER push to main. Only push your `orchestrator/abc-pubcookie-keyid` branch and open a PR.
- Do NOT apply any database migration, do NOT touch infra/Cloudflare/Terraform, do NOT make live secret-backed network calls. If the task seems to require any of these, ESCALATE.
- Stay in this worktree. Do not modify files outside it.
- No new runtime dependency in the tracker (it is zero-dep by contract).

## Notes

This is a small, well-scoped change across 3 packages (core encode, react middleware, tracker decode). The variant VALUE is already available pre-config; only the experiment ID is missing. Keep the diff minimal and the bundle lean.
