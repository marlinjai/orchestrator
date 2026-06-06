---
task: arbosano-seo-deliverables
---

# Goal

Produce ArboSano's real, data-backed SEO consulting deliverables using the DataForSEO CLI, replacing the shallow WebSearch estimates in `docs/pitch/KEYWORDS.md` with real search-volume, keyword-difficulty, ranking, and local-pack data. These deliverables back the Beratung (consulting) line items in the EUR 6.500 Angebot, so they must be client-grade: clear, sourced, decision-useful, and in German.

Write three files under `docs/pitch/deliverables/`:

1. `keyword-research.md` : real Google search volume plus keyword difficulty per umbrella and section for ArboSano's keyword set, plus a long-tail expansion, with concrete H1, URL-slug, and Meta-Title recommendations per page.
2. `competitor-serp-analysis.md` : real organic rankings for the core terms across the seven Berlin competitors, plus a local-pack / Google Business Profile gap analysis (where ArboSano can realistically win).
3. `tracking-concept.md` : a conversion and advertisement-tracking concept (GA4 plus Google Ads events, landing-anchor strategy per umbrella, a measurement plan tied to the keyword priorities).

## Read first

- `docs/pitch/KEYWORDS.md` : the existing R5 keyword snapshot (estimates, grouped by service and umbrella). Your keyword set starts from here.
- `docs/pitch/MARKTANALYSE.md` : the seven Berlin competitors (domains in section 1) and the market framing.
- `docs/pitch/leistungsumfang-arbosano.md` : the offer these deliverables support (the Beratung line items and service structure).
- `src/content/pages/*.ts` : the actual service pages (baumpflege, faellarbeiten, baumsicherheit, eps-behandlung, sachverstaendiger, gewerbe) for the exact services and section anchors.
- `.claude/skills/dataforseo/SKILL.md` if present : the full DataForSEO tool guide.

## DataForSEO tool: how to call it

The CLI binary is at `~/printing-press/library/dataforseo/dataforseo`. ALWAYS run it through the repo's Infisical wrapper so credentials inject (they live in Infisical, never in code):

    ./scripts/dev-secrets.sh ~/printing-press/library/dataforseo/dataforseo <command> --agent

- Health check first: `... doctor --agent` must show `auth: configured` and `env_vars: OK`. If it does not, STOP and report. Do not loop.
- ALWAYS `--dry-run` a new endpoint first to preview the request body (free, no credits). Then drop `--dry-run` for the real call.
- Body: pass a single task as a JSON object via `--body-json '{...}'`. The CLI auto-wraps it into DataForSEO's required top-level array `[{...}]`. Confirm with `--dry-run`.
- Location and language: Berlin City `location_code` 1003854, Germany `location_code` 2276, `language_code` "de". Resolve other towns with `serp google-locations` (free, cost 0).

Commands to use:

- Search volume (batch up to 1000 keywords in ONE call): `keywords-data google-ads-search-volume-live` with `{"keywords":[...],"location_code":1003854,"language_code":"de"}`.
- Keyword difficulty (batch): `dataforseo-labs google-bulk-keyword-difficulty-live`.
- Long-tail expansion: `dataforseo-labs google-keyword-suggestions-live` or `google-keyword-ideas-live` per seed term.
- Competitor ranked keywords: `dataforseo-labs google-ranked-keywords-live` with `{"target":"<competitor-domain>","location_code":1003854,"language_code":"de","limit":50}`.
- Rank check per core term (ONE call returns the whole SERP, so you see every competitor at once): `serp google-organic-live-advanced` with `{"keyword":"...","location_code":1003854,"language_code":"de"}`.
- Local pack: `serp google-local-finder-live-advanced`.
- Google Business Profile snapshot: `business-data google-my-business-info-live`.

## Cost guardrails (HARD)

Live calls cost DataForSEO credits. Stay frugal:

- BATCH keywords. One search-volume call and one bulk-difficulty call cover the entire keyword set (up to 1000 each). Do NOT loop one keyword per call.
- Cap live `serp google-organic-live-advanced` calls at about 15: pick the single strongest core term per service and section.
- Cap competitor `google-ranked-keywords-live` at the seven known domains, one call each.
- Cap local-pack plus GBP calls at about 8 combined.
- Total live calls across the whole run: aim for under 30. If you hit a credit or auth error, STOP and report. Never retry-loop a paid call.
- Save the raw JSON responses you rely on under `docs/pitch/deliverables/_raw/` so every number is auditable.

## Definition of done

- The three markdown files exist under `docs/pitch/deliverables/`, each client-grade, built from REAL DataForSEO numbers (not estimates), each with a short "Datenquelle und Stand" note (DataForSEO, date, location_code).
- Every search-volume and difficulty figure traces to a saved raw response in `docs/pitch/deliverables/_raw/`.
- A single commit on this branch with a conventional-commit message, for example `docs(pitch): data-backed SEO deliverables for the ArboSano Angebot`.
- Final message states the three file paths, the total number of live DataForSEO calls made, and any keyword or competitor you could not get data for.

## Constraints

- Stay in this worktree. Only create or modify files under `docs/pitch/deliverables/`. Do NOT touch `src/`, the existing pitch docs, the DataForSEO CLI, or anything else.
- Do not push to any remote and do not open a PR. The operator handles review and merge.
- Do not modify Infisical secrets.
- German output for the deliverables, matching the tone of the existing pitch docs. No em-dashes and no en-dashes anywhere (use colons, parentheses, commas, or new sentences).

## Notes

- The whole point is replacing the explicit "Schaetzungen, keine Daten aus Google Keyword Planner" caveat in KEYWORDS.md with real data. Lead with the real numbers.
- If `doctor` shows credentials missing, or a network or sandbox error blocks the API, STOP immediately and report. Do not burn iterations retrying.
