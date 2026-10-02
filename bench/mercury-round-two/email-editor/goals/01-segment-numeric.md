---
verify: cd packages/contacts && pnpm exec vitest run
---
# Numeric comparisons and list operators in the contact segment evaluator

Work in `packages/contacts/src/segment-evaluator.ts` and `packages/contacts/src/types.ts`.

Today `greater_than` and `less_than` compare the two values as strings, so a custom field
`age = "9"` counts as greater than `"10"`. Change the evaluator as follows.

## Ordering operators

`greater_than` and `less_than` keep their names, and two operators are added to the
`SegmentOperator` type: `greater_or_equal` and `less_or_equal`. All four follow one rule:

- Trim both the field value and the rule value. If both are non-empty and `Number(value)` is a
  finite number for both, compare them as numbers.
- Otherwise compare them as strings, case-insensitively (lower-case both, then use the ordinary
  `<`, `>`, `<=`, `>=` on the lower-cased, untrimmed strings).

Examples: field `"9"` is not `greater_than` `"10"`; field `"10"` is `greater_or_equal` `"10.0"`;
field `" 7 "` is `less_than` `"8"`; field `"banana"` is `greater_than` `"Apple"`; field `""` is
`less_than` `"5"` (string comparison, because one side is empty).

## List operators

Add `in` and `not_in` to `SegmentOperator`. The rule value is a comma-separated list. Each item
is trimmed and lower-cased, and empty items are ignored.

- For every field except `tags`: `in` is true when the trimmed, lower-cased field value equals
  one of the items.
- For the field `tags`: `in` is true when at least one of the contact's tags (each trimmed and
  lower-cased) equals one of the items. The tags are compared one by one, not as the joined
  string.
- `not_in` is the exact negation of `in`.
- With an empty list (for example the value `""` or `" , "`), `in` is false and `not_in` is true.

Examples: field `status = "active"` is `in` `"Active, bounced"`; a contact with tags
`["vip", "newsletter"]` is `in` `"beta, VIP"` and is `not_in` `"beta,gamma"`.

Every other operator keeps its current behavior.

Add or update tests for this behavior in `packages/contacts/src/__tests__/`. Run
`pnpm exec vitest run` inside `packages/contacts` until it passes, then commit your change with git
(`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change
the behavior of anything the task does not mention.
