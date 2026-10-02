---
verify: cd packages/contacts && pnpm exec vitest run
---
# Fallback values in merge fields

Work in `packages/contacts/src/merge-fields.ts`.

A merge field is written `{{first_name}}` today. Add an optional fallback, written after a
pipe: `{{first_name|there}}`.

## Placeholder syntax

A placeholder is `{{`, optional whitespace, a name made of word characters (`\w+`), optional
whitespace, then optionally a pipe `|` followed by the fallback text, then `}}`. The fallback
is every character up to the closing `}}` (it cannot contain `}`), with leading and trailing
whitespace removed. It may be empty. So `{{ first_name }}`, `{{first_name|there}}`,
`{{ first_name | dear customer }}` and `{{first_name|}}` are all placeholders. Anything else,
for example `{{first name}}` or `{{}}`, is not a placeholder and stays in the text untouched.

## resolveMergeFields

The lookup order stays as it is (built-in fields, then `extras`, then custom fields).

- A field that resolves to a non-empty string is replaced by that string.
- A field that resolves to an empty string, or is not known at all, is replaced by the fallback
  when the placeholder has one (an empty fallback gives an empty string).
- A field that resolves to an empty string and has no fallback is replaced by an empty string,
  as today.
- A field that is not known at all and has no fallback stays in the text exactly as it was
  written, including its whitespace.

`full_name` counts as empty when the contact has neither a first nor a last name.

Examples, for a contact with no first name and the custom field `company = "Acme"`:
`"Hi {{first_name|there}}!"` becomes `"Hi there!"`; `"{{ company | your company }}"` becomes
`"Acme"`; `"{{ nickname }}"` stays `"{{ nickname }}"`; `"{{nickname|}}"` becomes `""`.

## extractMergeFields

Returns the field names only (never the fallback), each once, in the order of first appearance,
for both forms of the placeholder.

## extractMergeFieldFallbacks (new export)

`extractMergeFieldFallbacks(content: string): Record<string, string>` returns, for every field
that has at least one placeholder with a fallback, the fallback of the first such placeholder.
Fields that never carry a fallback are not in the result. Export it from the package index
(`packages/contacts/src/index.ts`) next to the other merge-field functions.

Add or update tests for this behavior in `packages/contacts/src/__tests__/`. Run
`pnpm exec vitest run` inside `packages/contacts` until it passes, then commit your change with git
(`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change
the behavior of anything the task does not mention.
