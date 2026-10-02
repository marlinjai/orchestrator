---
verify: pnpm --filter @agentic-os/hud test
---
# Clearer failure results when switching the active company

Work in `apps/hud/src/lib/switch-company.ts`, in `switchActiveCompany(tenantId, fetchImpl)`.

Add three cases. Everything else (the request itself, the success result, the 403 and 400 results,
the network-error result and the generic fallback) stays exactly as it is.

1. **No company given.** When `tenantId`, after trimming whitespace, is empty, no request is
   made at all (`fetchImpl` is not called) and the result is
   `{ ok: false, retryable: false, message: "No company selected." }`.
   A non-empty id is sent as it was given, untrimmed.

2. **Session expired.** HTTP 401 gives
   `{ ok: false, retryable: false, message: "Your session has expired. Sign in again." }`.

3. **Rate limited.** HTTP 429 gives `retryable: true`. The message depends on the response's
   `Retry-After` header (read with `res.headers.get("retry-after")`):
   - when the header, trimmed, is a whole number of seconds made only of digits and greater than
     zero: `"Too many attempts. Try again in N seconds."`, with `N` the number, and for exactly
     one second `"Too many attempts. Try again in 1 second."`;
   - in every other case (no header, no `headers` object on the response, a date, `0`, anything
     else): `"Too many attempts. Try again shortly."`.

Add or update tests for this behavior next to the module in `apps/hud/src/lib/` (files named
`*.test.ts`). Run `pnpm --filter @agentic-os/hud test` from the repository root until it passes,
then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit
with update_state. Do not change the behavior of anything the task does not mention.
