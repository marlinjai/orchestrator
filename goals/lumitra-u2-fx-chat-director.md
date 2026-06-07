---
task: lumitra-u2-fx-chat-director
spec: ~/software-dev/knowledge-base/research/2026-06-07-u2-fx-chat-director-plan.md
depends_on: [lumitra-u1-fx-adopt-schema]
shared_state: [lockfile]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
verify: pnpm install && pnpm -r --if-present run test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1200
---

# U2: FX chat director live on the landing hero (KIE-first, OpenRouter fallback)

READ THE PLAN FIRST and follow it exactly. Do NOT relitigate locked decisions:
~/software-dev/knowledge-base/research/2026-06-07-u2-fx-chat-director-plan.md
Frozen context: the strategy keystone 2026-05-31-lumitra-unified-platform-strategy.md (Phase U2)
and the U0 patch contract in @marlinjai/studio-scene-core (validatePatch, ScenePatch, findNode,
specToZod, listNodeDefinitions, runMigrations, sceneToJSON).

LOCKED: text LLM = KIE-first (Claude Sonnet/Opus via https://api.kie.ai/claude/v1/messages, Bearer
KIE_API_KEY, native tools/input_schema + tool_use, SSE). OpenRouter is the configured fallback.
Provider stays swappable. fal.ai untouched. The director is a stateless tool-use agent emitting
validated scene patches, NOT a chat box. Ships as a Next route in lumitra-web (already on Coolify).
Secrets via Infisical, PLACEHOLDER-first.

## What to build (lumitra-web)

Director core (pure, network-free) lives in its OWN new workspace package packages/director-core
(name @lumitra-web/director-core, private), deps @marlinjai/studio-scene-core, with its own vitest +
"test" script. It is NOT inside packages/fx (architecture: the director core is its own Tier-1
engine, destined for published @marlinjai/studio-director-core when the engine-monorepo migration
happens later; build it as its own package now so that later move is a relocate, not a rewrite):
1. toolSchema.ts: generate ONE `apply_scene_patch` tool input_schema from scene-core's registry
   (listNodeDefinitions + per-ParamSpec constraints, same switch as specToZod) AND the live Scene's
   node ids. The schema is a hint; validatePatch is the gate.
2. applyPatch.ts: applyScenePatch(scene, patch): Scene. Validate-then-apply, immutable (new Scene).
   scene-core has NO applyPatch; you build it. Cover all 5 ops; `set` is dominant.
3. loop.ts: runDirector(llm, scene, instruction): model turn -> tool_use -> validatePatch
   (fail-closed) -> on ok applyScenePatch + emit patch; on error feed result.error back as a
   tool_result for self-correction. Cap turns (~4). Stream text deltas.
4. provider.ts: DirectorLLM interface + deterministic stubDirectorLLM (the CI double; there is NO
   pre-existing stub).
5. index.ts barrel. The app imports the director core from @lumitra-web/director-core.

Network provider impls (app, Node-only, never in fx):
6. src/lib/director/kie.ts: thin fetch client, POST https://api.kie.ai/claude/v1/messages, Bearer
   KIE_API_KEY, Anthropic Messages body (system, tools, messages, stream:true), SSE parse of text +
   tool_use. Pin anthropic-version. NEVER enable web search.
7. src/lib/director/openrouter.ts: fetch /chat/completions, OpenAI tools/tool_calls, SSE. Fallback.
8. src/lib/director/select.ts: KIE_API_KEY -> kie; else OPENROUTER_API_KEY -> openrouter; else throw.

Route + UI:
9. src/app/api/director/route.ts: POST. Mirror src/app/api/health/route.ts conventions (read the
   non-standard Next docs in node_modules/next/dist/docs first). Read keys server-side only, select
   provider, run runDirector, stream SSE. 503 if no provider configured. Never log secrets.
10. src/components/DirectorChat.tsx ("use client"): input -> POST /api/director -> consume SSE ->
    onPatch(validatedPatch) callback. Ownership-framed PLACEHOLDER copy (human reviews).
11. Wire into the hero (src/components/IntroSequenceHero.tsx, or a new LiveHero it delegates to):
    hold the editable unified Scene in state (seed: runMigrations(v7Json) as Scene), derive
    config = sceneConfigFromUnified(scene), render <LumitraScene key={rev} config=...>. On each
    applied patch, setScene(applyScenePatch) and bump rev (LumitraScene seeds config once and only
    remounts on key change: verified LumitraScene.tsx:160-176). Add an Export button using scene-core
    sceneToJSON(scene) -> valid v2 JSON. KEEP HeroFallback, the WebGL gate, and the CTA overlay.
12. src/scenes/v7.ts: add `export const v7Scene = runMigrations(v7Json) as Scene;` alongside the
    existing v7SceneConfig (leave v7SceneConfig intact).

## Network-free contract test (under the director-core package's vitest)
packages/director-core/src/__tests__/director.contract.test.ts using stubDirectorLLM (NO network):
- a fixed instruction yields a validatePatch-passing `set` patch on a node present in v7 that
  applyScenePatch applies;
- an out-of-range instruction is rejected by validatePatch (fail-closed), scene unchanged, error
  fed back;
- toolSchemaFor(scene) ranges match the registry (drift guard).

## Secrets (operator-provisioned; Worker writes code only)
The Worker does NOT touch Infisical. Write code that reads process.env.KIE_API_KEY /
process.env.OPENROUTER_API_KEY server-side only (in the route / select.ts), with a clear 503 when
neither is set. The operator provisions KIE_API_KEY + OPENROUTER_API_KEY in lumitra-web's Infisical
project out-of-band (PLACEHOLDER first, real values by Marlin). NEVER run infisical from Bash, never
echo keys, never commit them. The build is headless (runtime-only key), so CI needs no secret.

## Acceptance
1. fx vitest green incl director.contract.test.ts. 2. typecheck + lint clean (app + fx).
3. pnpm build green (route compiles, no build-time secret). 4. Instruction -> validated patch ->
live hero mutation works in-browser (human smoke test with real key). 5. Export returns valid v2
JSON (round-trips through scene-core deserializeScene). 6. Section copy ownership-framed, zero
hosting-as-product language (human gate).

## Hard constraints
- Architecture is frozen. ADD; do not re-derive. KIE-first, OpenRouter fallback, swappable.
- validatePatch EVERY patch before apply (fail-closed); never apply raw model output. Self-correct
  on validation error.
- Do NOT touch the render path: packages/fx/src/LumitraScene.tsx and packages/fx/src/serialize.ts
  stay UNCHANGED. Do NOT touch any other route (api/health, designs/*, angebot/*, fx/gallery),
  next.config.ts, Dockerfile, CI, or infra.
- Do NOT enable KIE web search on the director call (mutually exclusive with function calling on the
  GPT path; the director only needs function calling).
- Do NOT deploy, publish, or run infisical/secrets-mutating commands. PLACEHOLDER-first only.
- Read node_modules/next/dist/docs before writing route code (this is NOT the Next.js you know).
- Conventional commits, body lines <= 100 chars, NO em-dashes / en-dashes. No --no-verify.
- Single branch; NEVER push to main; NEVER gh pr merge (operator merges after the copy + live-key
  human review).
