---
task: framer-p2-publish
spec: docs/specs/wave-2/static-html-publish-pipeline.md
verify: pnpm typecheck && pnpm test -- --run
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement framer-clone's P2 static publish pipeline: turn a built site (the persisted MST ProjectModel from P1) into a static HTML bundle, INCLUDING per-experiment-variant output and the analytics tracker snippet, written to a local/dry-run output target (NOT a live R2 bucket). This is the substrate the future edge hosting layer (P3/P4) serves. Build to the drafted Wave-2 spec.

## Read first

- The spec: `docs/specs/wave-2/static-html-publish-pipeline.md` (full contents: Goal, Scope, Files, API, Test plan, Definition of done). This is the authority.
- `docs/specs/wave-1/static-html-spike.md` (the per-page emitter shape) and `src/lib/renderer/publish/hydrateBindings.ts` (existing pure data-binding resolver).
- `src/lib/renderer/{HeadlessPageRenderer,HeadlessComponentRenderer}.tsx` (the render path; `renderToStaticMarkup` is the emit mechanism).
- `src/models/ProjectModel.ts` (the project/page model + `LumitraBindingModel` for the analytics binding) and the P1 site-persistence layer in `src/server/sites/*` (this branch is based on the P1 foundation; read what P1 added).
- `docs/plans/2026-06-23-framer-hosting-platform-foundation.md` (the P2 scope + how per-variant emit feeds the edge rewrite).

## What to build (per the spec; if the spec and this differ, the spec wins, note the divergence)

**Build-order reality (do NOT block on this).** The wave-1 per-page emitter the spec leans on (`emitStaticHtmlForPage` in `src/lib/renderer/publish/staticHtmlEmitter.ts`) and the `static-html-spike` / `static-html-css-flattener` specs DO NOT EXIST in the tree yet. Build the minimal per-page emitter INLINE as part of this task, using `react-dom/server.renderToStaticMarkup` on `HeadlessPageRenderer` (the spike's intended API). Do NOT stall hunting for the missing spike, and do NOT balloon scope by inventing a separate CSS-flattener package: inline the smallest CSS handling that yields a working static page and note that choice in the PR. `PageModel` already has a `slug` field, so the spec's slug open-question is resolved.

- `projectPublisher.ts` (entry: `publishProject(project, options)`), `assetCollector.ts`, and the per-page `staticHtmlEmitter.ts`, emitting `<slug>/index.html` + flattened CSS + assets + a `manifest.json`.
- Per-VARIANT emit: when a site has running experiments, emit one artifact set per variant under a namespaced key (e.g. `_exp/<experimentKey>/<variant>/<page>/index.html`) plus the control baseline, so a future edge rewrite can select an arm. Keep it bounded; if the variant combination count is large, log/cap it (never silently truncate).
- Tracker snippet injection on publish: inject the analytics tracker init + the `window.__AP_VARIANTS` bridge into the emitted HTML head, resolving the binding's key reference server-side (do NOT embed any real secret beyond the public-by-design ingestion key the binding already models).
- Output target: write to a LOCAL output directory (a dry-run/local emitter). Provide a clean seam where a real R2 uploader would plug in later, but DO NOT implement or call real R2/Cloudflare.

## Definition of done

- Whatever the spec's Definition of done lists, PLUS the `verify` gate passes (typecheck + full test run).
- Flip ONLY the spec's own frontmatter `status: draft` to `status: done`. Do NOT try to reconcile `docs/specs/STATUS.md` (it has been superseded by a newer track system); skip that ledger to avoid wasting cycles on a stale doc.
- `git push -u origin orchestrator/framer-p2-publish` then open a PR: `gh pr create --base feat/p1-auth-brain-foundation --title "feat(framer): P2 static publish pipeline (per-variant emit + tracker snippet)" --body "<what/why/how-verified>. Stacked on the P1 foundation PR; retarget to main after P1 merges."`. NO em-dashes/en-dashes. End the PR body with a blank line then: 🤖 Generated with [Claude Code](https://claude.com/claude-code)
- Conventional commit(s) describing the why.

## Constraints (hard, unattended overnight run)

- NEVER merge anything. NEVER push to main. Only push your `orchestrator/framer-p2-publish` branch and open the PR (base = `feat/p1-auth-brain-foundation`).
- Do NOT implement or call real R2/Cloudflare/any cloud upload; the output is a LOCAL directory only. Do NOT apply any DB migration. Do NOT make live secret-backed network calls. If the spec seems to require any live infra/secret/deploy step, implement the code seam and ESCALATE rather than executing it.
- Do NOT bolt in any end-user/shopper (CIAM) identity. That plane is explicitly out of scope and deferred to a separate buy/embed decision.
- Stay in this worktree. This is greenfield: if you hit a genuine architecture fork the spec does not resolve (e.g. CSS flattening strategy, asset hashing scheme) that you are not confident about, make the smallest reasonable choice, document it in the PR body as a decision-for-review, and keep going; ESCALATE only if blocked.

## Notes

This branch is based on `feat/p1-auth-brain-foundation` (P1 is not yet merged to framer main), so you HAVE P1's auth + site-persistence code. The PR is therefore stacked on P1. Greenfield against a drafted spec: lean on the spec, keep the diff coherent, and surface any decisions you made for Marlin's morning review.
