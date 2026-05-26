# Goal: ArboSano Speculative Pitch - Wave 2 (Build)

## Mission

You are running inside a git worktree of the arbosano repo on branch
`orchestrator/arbosano-pitch-wave2`. The worktree was created from the
`speculative-pitch-arbosano` branch which already contains the five
Wave 1 research docs under `docs/pitch/`.

Build the 10-page speculative pitch site driven by those docs. Render
German marketing copy in `[GENERATE]` slots in Marlin's voice. Wire
navigation per `SITEMAP.md`. Implement the block renderers R3 flagged
as missing. Configure 301 redirects from legacy WordPress paths to the
new clean slugs. Draft the Leistungsumfang offer doc.

Do NOT push to origin. Marlin cherry-picks back after review.
Do NOT configure Coolify, no domain, no email send, no security setup.

## Authoritative inputs (read-only)

- /Users/marlinjai/software-dev/arbosano/docs/superpowers/specs/2026-05-25-arbosano-speculative-pitch-design.md
- /Users/marlinjai/software-dev/arbosano/docs/superpowers/plans/2026-05-25-arbosano-speculative-pitch.md
- docs/pitch/CONTENT.md (authoritative facts; nothing outside this is true unless flagged)
- docs/pitch/SITEMAP.md (slug + nav decisions; LOCKED below)
- docs/pitch/PAGE-PLAN.md (block-by-block per page; LOCKED with overrides below)
- docs/pitch/VISUALS.md (image plan; real photos preferred, AI fallback)
- docs/pitch/KEYWORDS.md (primary keyword per service page)
- /Users/marlinjai/.claude/marlinjai.md (voice guide; mandatory)
- /Users/marlinjai/.claude/CLAUDE.md (typography rules: NO em-dashes, NO en-dashes)

## Locked decisions (override anything that contradicts)

### Slugs (FLAT pattern, override R3's nested proposals)

| Page | Slug |
| --- | --- |
| Startseite | `/` |
| ArboSano 360 fuer Gewerbekunden | `/gewerbe` |
| Ueber uns | `/ueber-uns` |
| Hauke Rudolph (Sachverstaendiger) | `/sachverstaendiger` |
| Baumkontrolle | `/baumkontrolle` |
| Baumgutachten | `/gutachten` |
| Baumfaellungen | `/faellungen` |
| Eichenprozessionsspinner | `/eps-behandlung` |
| Kontakt | `/kontakt` |
| Impressum | `/impressum` |
| Datenschutz | `/datenschutz` |

PAGE-PLAN.md uses `/leistungen/<service>` and `/team/hauke-rudolph` and
`/arbosano-360`. Override those; use the table above everywhere.

### 301 redirects from legacy WordPress paths

Configure in `next.config.ts` under `redirects()`:

| From (old WP path) | To (new slug) |
| --- | --- |
| `/baumpflege-dienstleistungen` | `/baumkontrolle` |
| `/baumkontrolle` | `/baumkontrolle` (no-op, but record) |
| `/baumkataster` | `/gewerbe` |
| `/gutachten` | `/gutachten` (no-op, record) |
| `/baumfaellarbeiten` | `/faellungen` |
| `/faellarbeiten-mit-der-seilklettertechnik` | `/faellungen` |
| `/eichenprozessionsspinner-entfernung` | `/eps-behandlung` |
| `/baumsicherheit` | `/baumkontrolle` |
| `/services` | `/` (no umbrella page in new IA; route to home + scroll to leistungen anchor not required) |
| `/team` | `/ueber-uns` |
| `/team/hauke-rudolph-baumpfleger` | `/sachverstaendiger` |
| `/team/vincent-schoenlau-baumpfleger` | `/ueber-uns` |
| `/ueber-uns` | `/ueber-uns` (no-op, record) |
| `/kontakt` | `/kontakt` (no-op, record) |
| `/360` | `/gewerbe` |
| `/datenschutzerklarung` | `/datenschutz` |

All redirects: `permanent: true` (= 308 in Next; Google treats as 301).
Include the no-ops as comments in the file so the SEO continuity story
is visible to anyone reading next.config.ts.

### [UNKNOWN] resolutions

- **Geographic claim**: use "Grossraum Berlin" (verbatim from old site).
  Do NOT claim Brandenburg coverage. Leave Brandenburg as Input ArboSano
  in the offer doc.
- **Office hours**: render as "Mo bis Fr 9 bis 15:30 Uhr". Flag as
  Input ArboSano in offer doc if Hauke wants different.
- **Maxim Wermke contact**: route through info@arbosano.de + 030 666 27448.
  Do NOT invent a direct line.
- Everything else in CONTENT.md section 8 stays Input ArboSano.

## Hard constraints

- Never invent facts beyond CONTENT.md. Gaps: write `[Inhalt folgt nach Abstimmung]`.
- Marketing copy: German, Sie-form, Marlin-voice per marlinjai.md.
- NEVER use `—` (U+2014) or `–` (U+2013) in any file you write. Em-dash sweep is a verification gate.
- Reuse existing block schemas under `src/collections/Pages.ts`. Do NOT add new block types. Renderers under `src/components/blocks/` are NEW work and expected.
- No edits to `payload.config.ts` schemas, no new Payload collections, no env changes, no dependency additions beyond what's already in package.json.
- Service pages MUST use their primary KEYWORDS.md keyword in H1, URL slug, and `<title>` meta:
  - `/baumkontrolle`: "Baumkontrolle Berlin" in H1 + title
  - `/gutachten`: "Baumgutachten Berlin" in H1 + title
  - `/faellungen`: "Baumfaellung Berlin" in H1 + title
  - `/eps-behandlung`: "Eichenprozessionsspinner entfernen Berlin" in H1 + title
- One commit per page (`pitch(<slug>): build page`), one commit for renderers, one commit for redirects, one commit for the offer doc.
- Branch: `orchestrator/arbosano-pitch-wave2`. Do not push.

## Renderer scope (NEW work, expected)

R3's PAGE-PLAN.md flagged these renderers as not yet wired. Build them
as colocated React components under `src/components/blocks/`:

- `<TextSection>` (props: heading, content rich-text, layout: narrow|two-col|full, darkBackground?)
- `<ImageBanner>` (props: image, alt, caption, layout: full-bleed|contained|split)
- `<ServicesGrid>` (props: mode: featured|all|manual, heading, intro, manualServices?, ctaLabel, ctaHref) - pulls from `services` collection when not manual
- `<TeamTeaser>` (props: heading, intro, members[]|memberSlugs[], darkBackground?) - pulls from `team` collection
- `<Testimonials>` (props: heading?, items[{quote, author, role, photo?}])
- `<Faq>` (props: heading, items[{question, answer}]) - accordion behavior
- `<Stats>` (props: heading, items[{value, label, note?}])
- `<Process>` (props: heading, intro?, steps[{title, description}])
- `<ServiceArea>` (props: heading, intro, centerLabel, districts[]) - stylized map placeholder if no real map data

Plus the dispatcher:

- A page renderer that loads a Pages document by slug from Payload and
  walks its `sections` blocks array, dispatching to the right component
  per `blockType`. Place at `src/app/(site)/[slug]/page.tsx` or equivalent
  per existing Next.js conventions in the repo.

Plus contact form:

- A `<ContactForm>` component for `/kontakt` that posts to Payload.
  If there's no existing form collection, create the messages collection
  inline OR fall back to a simple `/api/contact` route that stores
  submissions to a local file/log for the demo. Flag the choice in
  QUESTIONS.md.

## Pages to build (in this order)

R1 has rich content for all of these. Use PAGE-PLAN.md as the block
recipe, override slugs per the locked table above.

1. `/baumkontrolle` (flagship: has pricing, most material)
2. `/gutachten`
3. `/faellungen`
4. `/eps-behandlung`
5. `/sachverstaendiger`
6. `/gewerbe`
7. `/ueber-uns`
8. `/` (home; uses materials from many other pages)
9. `/kontakt`
10. `/impressum` + `/datenschutz`

Header + footer per SITEMAP.md sections 2 and 3.

## Parallel side-task: Leistungsumfang offer doc

Also produce `docs/pitch/leistungsumfang-arbosano.md` consuming the
same inputs. Structure per spec section "Offer Document Structure":

1. Strategie & Konzeption (mark bereits umgesetzt with staging link placeholder)
2. Design & Entwicklung (Next.js + Payload, our stack-flip vs. WordPress)
3. Inhalt & Struktur (per-page status table; Input ArboSano clearly flagged)
4. Qualitaetssicherung & Technik (incl. Google-Ads-Tauglichkeit + 301-redirects-for-SEO-continuity paragraph)
5. Was wir mitbringen, das im Angebot nicht steht
6. Offene Fragen an Sie (3 questions: Kundengewinnung, Top-Service-Begriffe, geografische Schwerpunkte)
7. Investition (no number; commit to quote within 48h of discovery answers; never name competitor)

Plus Lieferumfang section (3 milestones) and one-sentence cover paragraph.

German, Marlin-voice, no em-dashes or en-dashes.

### 301-redirects paragraph in section 4

Include verbatim (or close paraphrase) this thinking, German, Marlin voice:

> "Wir uebernehmen die alten WordPress-URLs nicht eins zu eins, sondern
> setzen klare neue Slugs (`/baumkontrolle`, `/gutachten`, `/faellungen`,
> `/eps-behandlung`). Damit Ihre vorhandenen Google-Treffer und
> existierenden externen Links nicht ins Leere laufen, leiten wir alle
> alten URLs per 301 auf die neuen weiter. So gewinnen Sie saubere URLs
> ohne den bisherigen Sichtbarkeitsaufbau zu verlieren."

Adjust phrasing for voice; keep the substance.

## Done criteria

- All 10 routes return 200 on `pnpm dev`.
- `pnpm tsc --noEmit` exits 0.
- `next.config.ts` has the redirect block; `curl -sI http://localhost:3000/baumpflege-dienstleistungen` returns 308 with `location: /baumkontrolle`.
- Em-dash sweep across all changed source + `docs/pitch/leistungsumfang-arbosano.md` returns 0 hits.
- Contact form posts successfully in dev (manual or scripted test).
- `docs/pitch/leistungsumfang-arbosano.md` exists, has all 7 sections, voice-compliant.
- `docs/pitch/QUESTIONS.md` exists (even if empty) so Wave 3 has a place to read open items.
- All commits land on `orchestrator/arbosano-pitch-wave2`. Do NOT push.

## Escalation rules

- A block schema needed by PAGE-PLAN.md is missing from `Pages.ts`: stop, ask Marlin (we explicitly forbade new block types).
- Lighthouse a11y < 90 on `/` or `/baumkontrolle` after the page is built: append to QUESTIONS.md and continue; Wave 3 fixes.
- TypeScript can't pass after reasonable effort: stop, ask Marlin.
- Em-dash sweep keeps failing despite auto-fix attempts: stop, ask Marlin.
- Working tree wasn't clean on entry: stop, ask Marlin.

## Out of scope

- Coolify configuration, domain wiring, security plugins, email send.
- New Payload collections or schema changes.
- Real photography retouching beyond what's in `public/` and the scraped assets.
- Google Ads campaign work.
- Production deploy.

This is Wave 2 only. Wave 3 is Marlin manual polish + staging + email.
