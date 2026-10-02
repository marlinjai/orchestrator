---
verify: pnpm --filter @agentic-os/hud test
---
# Notion cover position round trip and stricter upload names

Work in `apps/hud/src/lib/notion-cover-frontmatter.ts`.

## notionPositionFromBannerY (new export)

`bannerYFromNotion(position)` turns Notion's `page_cover_position` into the `banner_y` key.
Add the inverse, `notionPositionFromBannerY(y: number | null | undefined): number`:

- `null`, `undefined` or a number that is not finite gives `0.5` (the centred default, which
  is what a missing `banner_y` means).
- Otherwise clamp `y` to the range 0 to 1 and return `1 - y`, rounded to three decimal places.
- The result is never `-0`: `notionPositionFromBannerY(1)` is `0`.

For every position `p` between 0 and 1 with at most three decimals,
`notionPositionFromBannerY(bannerYFromNotion(p))` equals `p`.

## uploadedCoverName

`uploadedCoverName(hashHex, ext)` keeps returning `cover-<first ten characters of the
hash>.<ext>`, with these rules added:

- `hashHex` must be at least ten characters long and consist only of hexadecimal digits (either
  case); otherwise throw a `RangeError`. The ten characters are written in lower case.
- `ext` is normalised: surrounding whitespace removed, leading dots removed, lower-cased, and
  `jpeg` becomes `jpg`. After that it must be one of `png`, `jpg`, `webp`, `gif`;
  otherwise throw a `RangeError`.

Examples: `uploadedCoverName("3F2A9C1B04DEADBEEF", ".JPEG")` is `"cover-3f2a9c1b04.jpg"`;
`uploadedCoverName("3f2a9c1b0", "png")` (nine characters) throws; `uploadedCoverName("3f2a9c1b04", "svg")`
throws.

Add or update tests for this behavior next to the module in `apps/hud/src/lib/` (files named
`*.test.ts`). Run `pnpm --filter @agentic-os/hud test` from the repository root until it passes,
then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit
with update_state. Do not change the behavior of anything the task does not mention.
