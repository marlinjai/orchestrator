---
task: b5-pricing-and-tax
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b5-pricing-and-tax.md
depends_on: ["b4-catalog-schema"]
shared_state: ["prisma","migrations"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce engine b5 (pricing graph + catalog-side German tax_class + CreditNote)

This is part of the framer-clone build (build-2026-06, commerce-engine track, wave 2). Build EXACTLY the b5-pricing-and-tax spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b5-pricing-and-tax.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Pricing graph in `prisma/schema.prisma`: `price_set` (pset), `price` (price; currency_code; amount as integer minor units / cents; min/max_quantity; belongsTo price_set + nullable price_list), `price_rule` (prule; attribute/value/operator/priority), `price_list` (plist; status enum; type; starts_at/ends_at). Money is integer cents, NEVER floats, NEVER Yjs.
- Catalog-side `tax_class` on `product` and `product_variant` (the tax CLASSIFICATION only, mapping to a future bought tax engine's product-tax-code). This is the ONLY tax surface b5 owns.
- `CreditNote` (Storno/Gutschrift) entity plus a `credit_note_ref` junction, because a German invoice cannot be DELETEd. b5 builds the entity plus the no-DELETE-on-invoice contract; the FK to the corrected Order/invoice is wired by b6 (which owns Order). Use a loose corrected_ref or a deferred FK so b5 does not block on a model it does not own.
- `src/server/commerce/repository/pricing.ts`: `PricingRepository` (`createPriceSet`, `addPrice`, `resolvePrice(tx, variantId, {currency, priceListIds})` returning integer cents) as a pure read over `tx`.
- `src/server/commerce/repository/__tests__/pricing.itest.ts` (integration): cents round-trip (integer, never float), price-list resolution returning integer cents for a variant, `tax_class` set/read on product/variant, and the CreditNote no-DELETE contract.
- A new migration under `prisma/migrations/**` for the pricing graph + `tax_class` + `CreditNote`.

## Hard constraints (do NOT)

- Shared state: this spec touches `prisma` and `migrations`. It APPENDS to the SAME `prisma/schema.prisma` (commerce schema specs b2-b6 edit it serially) at the SERIAL position after b4 and before b6. Do NOT run concurrently with another prisma/migrations writer. Touch no shared state owned by another spec beyond the declared `prisma` and `migrations`.
- Do NOT add any `Order.*` fields and do NOT create the Order model. Order-level tax fields (tax_region/vat_id/customer_type/reverse_charge/net_or_gross/kleinunternehmer) and the reverse-charge/Kleinunternehmer ORDER tests are OWNED by b6. The schema diff must touch NO Order model.
- Do NOT build the bought tax-engine call, OSS accumulation, or invoice rendering (those are E8). b5 ships only the catalog-side `tax_class`, the pricing graph, and the `CreditNote` entity.
- Resolver stays React-free and Node-evaluable: `PricingRepository.resolvePrice` is a pure read over `tx`, no React imports, runnable under the node vitest project.
- Keep changes minimal. Do NOT build any other spec's surface (no other commerce specs' models, no CMS surface, no UI). Do NOT add deps beyond what this spec needs.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed (no silent failures that look like success).
- Secrets via Infisical only, never `.env`, never a literal.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section: PriceSet/Price (integer cents)/PriceRule/PriceList land; `tax_class` on product/variant; `CreditNote` entity with the no-DELETE contract; b5 adds NO `Order.*` fields and creates no Order model (schema diff touches no Order model); `resolvePrice` returns integer cents over `tx` with cents round-trip + price-list tests passing; `pnpm exec prisma generate` + migration apply succeed; STATUS row flipped. Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with the placeholder `DATABASE_URL` for the build step.
