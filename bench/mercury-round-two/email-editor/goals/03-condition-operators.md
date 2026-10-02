---
verify: cd packages/automation && pnpm exec vitest run
---
# More operators and nested event data in the automation condition evaluator

Work in `packages/automation/src/condition-evaluator.ts` and `packages/automation/src/types.ts`.

## New operators

Add these to the `operator` union of `ConditionRule` and to `evaluateRule`:

- `starts_with`: the field value starts with `rule.value` (case-sensitive, like `contains`).
- `ends_with`: the field value ends with `rule.value` (case-sensitive).
- `is_empty`: the field value is the empty string. `rule.value` is ignored.
- `is_not_empty`: the field value is not the empty string. `rule.value` is ignored.
- `matches_any`: `rule.value` is a comma-separated list; each item is trimmed and empty items are
  ignored. For every field except `contact.tags` the rule is true when the field value equals one
  of the items exactly (case-sensitive). For `contact.tags` it is true when at least one of the
  contact's tags equals one of the items. An empty list is never matched.

## Numeric comparisons

`greater_than` and `less_than` are true only when both the field value and `rule.value`, after
trimming, are non-empty and `Number(...)` of each is finite; then they compare as numbers. In
every other case they are false. (Today an empty field counts as `0`.)

## Nested event data

`eventData` fields may be nested. A field path `eventData.a.b.c` walks into nested plain objects
key by key. The resolved value becomes a string like this:

- a string, number or boolean: `String(value)`;
- an array: its elements, each turned into a string with `String(...)`, joined with `,`;
- `null`, `undefined`, a missing key at any level, or a plain object at the end of the path:
  the empty string.

A path that tries to walk into something that is not a plain object (for example
`eventData.total.cents` when `total` is a number) resolves to the empty string. The one-level form
`eventData.key` keeps working with the same conversion rules.

Examples: with `eventData = { order: { total: 120, items: ["a", "b"] }, vip: true }`,
`eventData.order.total` is `"120"`, `eventData.order.items` is `"a,b"`, `eventData.vip` is
`"true"`, and `eventData.order` and `eventData.order.missing.deep` are `""`.

Every other operator and every `contact.` and `engagement.` path keeps its current behavior.

Add or update tests for this behavior in `packages/automation/src/__tests__/`. Run
`pnpm exec vitest run` inside `packages/automation` until it passes, then commit your change with git
(`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change
the behavior of anything the task does not mention.
