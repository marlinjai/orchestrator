# Goal: ArboSano Speculative Pitch - Wave 1 (Research)

## Mission

You are running inside a git worktree of the arbosano repo. The worktree
already lives on its own branch (`orchestrator/arbosano-pitch-wave1`);
do NOT create a new branch. Produce the five research documents that
Wave 2 will consume to build the speculative pitch site for ArboSano.
Run five research agents in two stages (R1 alone, then R2-R5 in parallel
against R1's output). Do NOT build any site pages in this run.

## Authoritative spec

- /Users/marlinjai/software-dev/arbosano/docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
- /Users/marlinjai/software-dev/arbosano/docs/superpowers/plans/2026-05-25-arbosano-speculative-pitch.md (Phase 0 + Phase 1 sections)

Read both before starting.

## Repo state precondition

- You are on branch `orchestrator/arbosano-pitch-wave1` inside a worktree.
- Working tree must be clean. If not, escalate.

## Phase 0: Setup

1. Create `docs/pitch/` directory with a `.gitkeep`.
2. Diff `arbosano_old_website_assets/` vs `arbosano_old_webste_assets/`:
   - If identical: delete the typo'd duplicate.
   - If they differ: keep both; record the diff in
     `docs/pitch/asset-reconcile-notes.md` for R1.
3. Commit: `pitch: scaffold docs/pitch/ for ArboSano speculative build`

## Phase 1: Wave 1 research agents

### Stage 1: Agent R1 alone

Dispatch R1 (fact extractor) as a subagent. Prompt verbatim:

```
You are R1, the fact-extractor agent for the ArboSano speculative pitch build.

CONTEXT
ArboSano is a Berlin tree-care business. We are building a speculative
preview of their website to win a deal against a competing agency. The
spec lives at docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md.
Read that spec first.

YOUR JOB
Read these source assets and extract every concrete fact about ArboSano.

Sources (all under /Users/marlinjai/software-dev/arbosano/):
- arbosano_old_website_assets/
- arbosano_old_webste_assets/ (typo'd duplicate if still present; reconcile)
- arbosano_old_website_assets/ArboSano360-PAKET-Digital-Version.pdf

OUTPUT
Write docs/pitch/CONTENT.md with these sections, in this order:
  1. Services offered (verbatim from sources, German)
  2. Certifications & qualifications (Hauke's Sachverstaendigen-status if present, ISA certs, TUEV, etc.)
  3. Team (names, roles, anything biographical)
  4. Contact details (address, phone, email, hours)
  5. Geographic service area
  6. Tone-of-voice samples (3-5 representative sentences pulled verbatim from old copy)
  7. Photography inventory (table: filename | what it shows | usable yes/no | notes)
  8. Facts NOT in sources but needed for a real site (flag every entry [UNKNOWN])
  9. Source-conflict log (if old website assets and PDF disagree)

HARD RULES
- Do not invent anything. If a source doesn't say it, it's [UNKNOWN].
- Quote services and certifications verbatim where possible.
- Mark every PDF-page or filename you pulled a fact from inline like (src: PDF p.4).
- No em-dashes (U+2014), no en-dashes (U+2013), per /Users/marlinjai/.claude/CLAUDE.md.

Report when CONTENT.md is written. Under 250 words in your reply.
```

Verify after R1 completes:
- `test -f docs/pitch/CONTENT.md` returns 0
- File has all 9 numbered sections
- `grep -c "—\|–" docs/pitch/CONTENT.md` returns 0

Commit: `pitch(wave1): R1 fact extraction from old assets + PDF`

### Stage 2: R2, R3, R4, R5 in parallel

Dispatch all four agents in ONE message (parallel) so they run concurrently.
Each agent reads docs/pitch/CONTENT.md as its authoritative input.

Prompts verbatim:

#### R2 (IA & sitemap)

```
You are R2, the IA agent for the ArboSano speculative pitch.

Read:
  - docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
  - docs/pitch/CONTENT.md (authoritative facts)

Competitor's 10-page list (target scope):
  1. Startseite / Landing
  2. Gewerbe / 360-Grad
  3. Ueber uns / Team & Fuhrpark
  4. Hauke-Page (Gutachterseite)
  5. Service-Landingpage: Baumkontrolle
  6. Service-Landingpage: Gutachten
  7. Service-Landingpage: Faellungen
  8. Service-Landingpage: EPS
  9. Kontakt / Rueckruf-Service
  10. Impressum / Datenschutz

OUTPUT
Write docs/pitch/SITEMAP.md containing:
  - Final 10-page list with German URL slugs (e.g., /baumkontrolle)
  - Header nav (5-6 primary items, in order)
  - Footer nav (legal + secondary)
  - Breadcrumb logic for the 4 service-landingpages
  - User-journey notes: Landing -> Service -> Kontakt golden path
  - Cross-link map (which pages link to which, beyond global nav)

Constraints: no em-dashes, no en-dashes.

Report when written. Under 200 words.
```

#### R3 (block mapping)

```
You are R3, the block-mapping agent for the ArboSano speculative pitch.

Read:
  - docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
  - docs/pitch/CONTENT.md
  - src/components/ (existing components, especially HomeSections.tsx, hero/, headers/)
  - src/collections/Pages.ts (Payload page block definitions)
  - src/app/(site)/ existing routes

OUTPUT
Write docs/pitch/PAGE-PLAN.md with one section per page (10 sections total).

For each page:
  ## <slug> - <German page title>
  Hero variant: <bone | soft-green | frosted-mask>
  Blocks (in render order):
    1. <BlockName> - content: <pulled from CONTENT.md or [GENERATE: <copy brief>]>
    2. ...
  Meta:
    title: <German SEO title>
    description: [GENERATE for Wave 2]

At the end add a 'Blocks we still need' section listing any block not in
src/components/ or Payload Pages.ts that PAGE-PLAN.md references.

HARD RULES
- Only reference blocks that already exist, unless flagged in the
  'Blocks we still need' section.
- Every content slot is either a verbatim quote from CONTENT.md or
  [GENERATE: <one-sentence brief>].
- No em-dashes, no en-dashes.

Report when written. Under 200 words.
```

#### R4 (visuals)

```
You are R4, the visuals-plan agent for the ArboSano speculative pitch.

Read:
  - docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
  - docs/pitch/CONTENT.md (photography inventory section)
  - public/ (existing images shipped with the site)
  - arbosano_old_website_assets/ (raw photos from old site)

OUTPUT
Write docs/pitch/VISUALS.md with one section per page. For each page:
  ## <slug>
  Hero image: <path/to/existing.jpg> OR
              [AI-GENERATE: nano-banana-2 prompt for placeholder]
              Label every AI image clearly: "Beispielbild: bitte ersetzen."
  Inline images: <list>

At the end:
  - 'Real photo inventory' table (filename, suitable for which page, license)
  - 'AI generation queue' table (page, prompt, target filename)

HARD RULES
- Prefer real photos over AI generation wherever a usable photo exists.
- Every AI image gets the "Beispielbild" label baked into the offer doc page-status table.
- No em-dashes, no en-dashes.

Report when written. Under 200 words.
```

#### R5 (keywords)

```
You are R5, the keyword-snapshot agent for the ArboSano speculative pitch.

Read:
  - docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
  - docs/pitch/CONTENT.md (services list)

JOB
For each of the four service-landingpages (Baumkontrolle, Gutachten,
Faellungen, EPS Behandlung), use WebSearch to find the top 3-5 German
search terms a Berlin tree-care customer would actually search.

For each keyword, capture:
  - Search term (German)
  - Rough volume tier (high / medium / low / niche)
  - Top 3 currently-ranking domains on Google.de
  - Search intent (informational / commercial / urgent-service)

OUTPUT
Write docs/pitch/KEYWORDS.md with one section per service. Recommend:
  - Primary keyword (for H1 + URL slug + meta-description)
  - 2-3 secondary keywords (for body copy)

HARD RULES
- This is a shallow pass. Do not propose campaign budgets, do not
  rank-track. Goal is keyword-aware on-page copy, not full SEO.
- German keywords only.
- No em-dashes, no en-dashes.

Report when written. Under 250 words.
```

Verify all four output files exist and are non-empty.
Em-dash sweep across all five docs:
`grep -rn "—\|–" docs/pitch/ || echo clean`
Expected: `clean`.

Commit: `pitch(wave1): R2-R5 sitemap, page plan, visuals, keywords`

## Done criteria

- All commits land on the worktree's branch (`orchestrator/arbosano-pitch-wave1`). Do NOT push to origin. Marlin will cherry-pick after review.
- All five files present and non-empty:
  - docs/pitch/CONTENT.md
  - docs/pitch/SITEMAP.md
  - docs/pitch/PAGE-PLAN.md
  - docs/pitch/VISUALS.md
  - docs/pitch/KEYWORDS.md
- Zero em-dashes or en-dashes anywhere under docs/pitch/.
- Final summary report listing:
  - Open questions / facts that R1 marked [UNKNOWN]
  - Any source-conflicts in CONTENT.md
  - Any blocks flagged as "we still need" in PAGE-PLAN.md
  - Any AI generations queued in VISUALS.md (so Marlin can sanity-check before Wave 2 spends tokens)

## Escalation rules

- Working tree not clean on `main`: stop, ask Marlin.
- R1 finds zero photographic assets: continue but flag prominently in the
  final summary; Wave 2 will rely entirely on AI placeholders.
- Any agent reports it couldn't read its input files: stop, ask Marlin.
- Em-dash sweep fails after auto-fix attempt: stop, ask Marlin.

## Out of scope

- Building any /src/app/(site)/ pages.
- Writing the Leistungsumfang offer doc.
- Configuring Coolify or staging.
- Sending any emails.

This is Wave 1 only. Wave 2 ships separately after Marlin reviews these
five docs.
