---
type: plan
status: in-progress
date: 2026-05-25
title: Unified marlinjai/bootstrap with profile-driven installation
summary: Collapse Lola-Stories/bootstrap and dotfiles/install.sh into a single public marlinjai/bootstrap repo with profile selection (lola-contributor, marlin-dev, custom). Infisical-first secret handling baked in.
tags: [bootstrap, dotfiles, lola-stories, orchestrator, infisical, dx]
projects: [orchestrator, dotfiles, lola-stories]
phase_status:
  phase_1_scaffold: completed (2026-05-25, merged at marlinjai/bootstrap@c3c6249)
  phase_2_lola_contributor: completed (2026-05-25, merged to Lola-Stories/bootstrap via PR #3)
  phase_3_dotfiles_absorption: queued (requires interactive --reconcile against Marlin's live laptop)
  phase_4_custom_multiselect: queued
  phase_5_infisical_enforcement: queued
---

# Unified marlinjai/bootstrap

## Why this plan exists

Today there are two scripts that bootstrap Marlin-flavored machines:

- `Lola-Stories/bootstrap/install.sh` (public, ~25 min, lean): brews, identity prompts, SSH key, clones Lola monorepo, builds the trello-pp-cli binary.
- `~/software-dev/dotfiles/install.sh` (254 lines, fat): Ableton/Adobe/Blender + 50 VS Code extensions, iTerm2 plist keybindings, MCP servers, ~19 Claude skills symlinked, orchestrator CLI install.

They overlap on the dev plumbing (brew, claude-code, zsh, node/uv/postgres) and diverge on personal creative stack + skills + MCP (Marlin-only) vs identity prompts + lola monorepo + trello-pp-cli (Lola-only). The handover at `docs/handovers/2026-05-25-tooling-baseline-bootstrap.md` originally framed this as "push the missing tool repos and add a Lola contributor script", but the actual situation has Lola-Stories/bootstrap already in production and the missing piece is just orchestrator + skills propagation.

Three failed framings to discard:

1. **Two parallel scripts (status quo).** Drift accumulates the moment one is touched. Brewfile entries get out of sync, claude-code install one-liner drifts, zsh setup divergences. Already happening.
2. **Lola/bootstrap clones dotfiles.** Leaks Ableton + Marlin's literal `gitconfig` + 10 personal-only skills + MCP servers with personal API keys onto every contributor's machine.
3. **Third repo `marlinjai/claude-skills`.** Solves skills-drift but creates three sources of truth and does not unify the brew/zsh/identity overlap.

The clean design is one repo with composable modules and a profile selector at startup. `Lola-Stories/bootstrap` becomes a 3-line wrapper that calls `marlinjai/bootstrap --profile lola-contributor`.

## Target shape

```bash
# Contributor flow (unchanged externally):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Lola-Stories/bootstrap/main/install.sh)"
# Lola/bootstrap is now a 3-line wrapper that curls marlinjai/bootstrap and runs:
#   ./bootstrap --profile lola-contributor

# Marlin's flow (new machine):
gh repo clone marlinjai/bootstrap && cd bootstrap && ./bootstrap --profile marlin-dev

# Anyone wanting opt-in modules:
./bootstrap --profile custom
# interactive multi-select drawn from the module registry
```

### Profiles

| Profile | Modules included |
|---------|------------------|
| `lola-contributor` | `homebrew-lean`, `claude-code-install`, `identity-prompts`, `ssh-key-upload`, `infisical-login`, `lola-monorepo`, `trello-pp-cli`, `colima-start`, `gitconfig-template`, `zsh-baseline` |
| `marlin-dev` | all of lola-contributor + `homebrew-fat` (Ableton, Adobe, etc.), `tmux-tpm`, `iterm2-keybindings`, `dotfiles-symlinks` (zshrc, gitconfig, aliases), `claude-skills-marlin`, `mcp-servers`, `orchestrator-cli`, `vscode-extensions` |
| `custom` | interactive multi-select over the full module registry |

### Modules

Each module is a directory under `modules/<name>/` with:

- `manifest.yaml`: name, description, profile tags, depends_on, requires_secrets, est_duration_sec
- `install.sh`: idempotent install logic, called as a function (not exec'd as separate process, so it shares env + sudo keep-alive)
- Optional `verify.sh`: post-install assertion (binary on PATH, file exists, command exits 0)

Registry is built by globbing `modules/*/manifest.yaml`. The profile selector and the custom-mode multi-select both read from this registry, so adding a module is one new directory.

### Infisical-first secret handling

Convention across all Marlin projects: secrets live in self-hosted Infisical at `https://infisical.lumitra.co`, never in literal env vars or `.env` files. The bootstrap enforces this:

1. After Homebrew, `infisical-login` module is mandatory across all profiles. It runs `infisical login --domain https://infisical.lumitra.co` and waits for browser-auth completion.
2. Modules that need secrets declare them in `manifest.yaml` via `requires_secrets: [ANTHROPIC_API_KEY, ...]`. The bootstrap reads these from the user's Infisical workspace and exports them via `infisical run` wrappers when invoking module logic, never as raw env vars.
3. Post-install, the bootstrap writes per-tool aliases (like the existing `trello` alias) that wrap the binary in `infisical run --env=...` so the tool always gets fresh secrets without disk persistence.

### Module list (initial set)

| Module | Profile tags | Depends on | Notes |
|--------|-------------|------------|-------|
| `xcode-clt` | all | none | gate on `xcode-select -p` |
| `homebrew` | all | xcode-clt | install brew itself |
| `homebrew-lean` | lola-contributor, marlin-dev | homebrew | the current Lola/bootstrap Brewfile (30 brews, ~20 casks) |
| `homebrew-fat` | marlin-dev | homebrew-lean | additional brews + casks from dotfiles/Brewfile (Ableton, Adobe, Blender, ~50 VS Code extensions) |
| `identity-prompts` | all | none | FULL_NAME, EMAIL, GH_USER |
| `gitconfig-template` | all | identity-prompts | renders from template. Used by every profile including marlin-dev. No profile ever symlinks Marlin's literal gitconfig. |
| `ssh-key-upload` | all | identity-prompts | ed25519 + `gh ssh-key add` |
| `zsh-baseline` | all | homebrew | starship + zsh plugins + symlink zshrc |
| `tmux-tpm` | marlin-dev | homebrew | symlink tmux.conf + clone TPM |
| `iterm2-keybindings` | marlin-dev | none | PlistBuddy patches, mac-only laptop module |
| `claude-code-install` | all | none | official one-liner |
| `claude-skills-marlin` | marlin-dev | claude-code-install | symlinks contributor-relevant skills (`release`, `frontend-design`, `find-skills`) + Marlin-personal skills (`knowledge`, `youtube-transcript`, etc.) |
| `claude-skills-contributor` | lola-contributor (opt-in via prompt) | claude-code-install | symlinks only contributor-relevant subset (`release`, `frontend-design`, `find-skills`) |
| `mcp-servers` | marlin-dev | claude-code-install, infisical-login | registers user-mcp.json with envsubst-expanded Infisical secrets |
| `infisical-login` | all | homebrew | mandatory; runs `infisical login --domain https://infisical.lumitra.co` |
| `colima-start` | lola-contributor, marlin-dev | homebrew | `colima start` if not running |
| `lola-monorepo` | lola-contributor, marlin-dev (opt-in) | ssh-key-upload | clone, `pnpm install`, `prisma generate` |
| `printing-press` | lola-contributor, marlin-dev | homebrew | install `printing-press` generator |
| `trello-pp-cli` | lola-contributor, marlin-dev | printing-press, infisical-login | clone+build `Lola-Stories/trello-pp-cli`, add `trello` alias |
| `orchestrator-cli` | marlin-dev, lola-contributor (opt-in) | homebrew | `uv tool install git+https://github.com/marlinjai/orchestrator` |
| `vscode-extensions` | marlin-dev | homebrew | ~50 ext install list |

The `claude-skills-marlin` module covers the contributor subset (`release`, `frontend-design`, `find-skills`) plus Marlin's personal skills (`knowledge`, `youtube-transcript`, `nano-banana-2`, etc.). The `claude-skills-contributor` module covers only the contributor subset. Both pull from the same source directory (`modules/claude-skills-source/`) so the per-skill metadata lives in one place, but the install logic differs in which subset gets symlinked.

## Implementation phases

### Phase 1: scaffold and registry

- Create `marlinjai/bootstrap` public repo
- Write `bootstrap` entrypoint script that parses `--profile` flag, loads registry, runs modules in dependency order
- Stand up the module loader (manifest.yaml parser, dependency resolver, idempotency check)
- Empty modules with just `manifest.yaml` and a placeholder `install.sh` that echoes the module name
- Verify the wiring: `./bootstrap --profile lola-contributor --dry-run` prints the correct module sequence

### Phase 2: port lola-contributor profile

- Migrate every step from `Lola-Stories/bootstrap/install.sh` into the corresponding module
- Run end-to-end against a fresh VM (or `colima`-managed clean macOS image if available; otherwise a recent git-cloned blank user dir)
- Verify the contributor checklist still works: `pnpm dev`, `trello doctor`, `infisical secrets get`
- Wire `Lola-Stories/bootstrap/install.sh` as a 3-line wrapper:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  exec /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/marlinjai/bootstrap/main/install.sh)" -- --profile lola-contributor "$@"
  ```
- Update `Lola-Stories/bootstrap/README.md` to point at the unified repo for module details

### Phase 3: port marlin-dev profile and absorb dotfiles

- Audit pass first: classify every file in `~/software-dev/dotfiles/` as `personal-literal` (never propagate; e.g. Marlin's `gitconfig`), `personal-templated` (template + prompt; e.g. anywhere `$HOME/software-dev/*` is hardcoded that other users would not have), or `universal` (carries over as-is; e.g. `tmux.conf`, the contributor skill subset)
- Migrate `~/software-dev/dotfiles/install.sh` content into modules
- Move static content into the modules that install it: `modules/claude-skills/skills/*`, `modules/zsh-baseline/zshrc`, `modules/tmux-tpm/tmux.conf`, `modules/iterm2-keybindings/custom-keys.json`, `modules/mcp-servers/user-mcp.json`, `modules/claude-code-install/settings.json` template, `modules/gitconfig-template/gitconfig.template`. Marlin's literal `gitconfig` is intentionally not migrated.
- The MCP registration becomes `mcp-servers` module with Infisical secret resolution
- The orchestrator install becomes `orchestrator-cli` module
- Verify against Marlin's existing laptop: run `./bootstrap --profile marlin-dev --reconcile` (a mode that lists what would change without changing it) and confirm no drift from the current state
- Freeze direct edits to `~/software-dev/dotfiles` for the duration of this phase (announce in dotfiles README + this plan)
- Once reconciliation is clean: archive the `~/software-dev/dotfiles` GitHub repo. Local checkout can stay for git history; new edits go to `marlinjai/bootstrap`. The archive is reversible if a regression surfaces.

### Phase 4: custom-mode multi-select

- Interactive picker (gum, fzf, or built-in `read` loop) that lets a user toggle modules
- Saves the selection to `~/.marlinjai-bootstrap-profile.local` so re-runs replay
- Document recipes for common partial setups (e.g. "claude-code only", "secrets-only refresh")

### Phase 5: Infisical-first secret enforcement

- Add a pre-flight check: if any selected module declares `requires_secrets`, the bootstrap halts before that module if `infisical-login` has not been completed
- Add a `bootstrap doctor` subcommand that verifies all module-declared secrets are present in the user's Infisical workspace, prints a checklist of what's missing
- Wrap orchestrator invocations in `infisical run` by default once `orchestrator-cli` module installs

## What this session delivers

- This plan, written and committed as `status: draft` for review.
- Orchestrator pushed to `https://github.com/marlinjai/orchestrator` (done at commit `f3ac8b2`, public).
- ROADMAP follow-up entry updated: "tooling baseline bootstrap" moves from open to in-progress with this plan as the resolution path.
- Handover doc `docs/handovers/2026-05-25-tooling-baseline-bootstrap.md` updated to mark scope-discovery resolution and point at this plan.

No edits to Lola-Stories/bootstrap or dotfiles/install.sh in this session. Both stay as the legacy paths until Phase 2 + 3 land.

## Open questions for Marlin

1. Should `claude-skills-contributor` (the lean subset) be opt-in or default-on for the `lola-contributor` profile? Default-on would mean every Lola contributor gets `release` + `frontend-design` + `find-skills` without choosing. Lean is good but only the ones we are confident are universally helpful belong in default-on.
2. Resolved 2026-05-25: never symlink Marlin's literal `gitconfig`, even under `marlin-dev`. A non-Marlin user picking `marlin-dev` (or assembling a similar set via `custom`) must not end up committing as Marlin. All profiles route through `gitconfig-template` + `identity-prompts`. Marlin's identity is cached in `~/.bootstrap-identity.local` after the first prompt so re-runs do not re-ask. Same rule applies to any other dotfiles content with hardcoded personal data (audit during Phase 3: zshrc paths, ssh config, gpg config if present, any `claude/settings.local.json` overrides).
3. Resolved 2026-05-25: `lola-monorepo` and `trello-pp-cli` modules are NOT available in `custom` mode for non-Lola users. The registry tags both modules `org_gated: Lola-Stories`. The custom-mode picker calls `gh api orgs/Lola-Stories/members/$GH_USER` (silent 404 = non-member); org-gated modules are hidden from non-members entirely. On the `lola-contributor` profile the same check happens up-front; non-members get a clear error explaining they need an invite before the bootstrap proceeds.
4. Resolved 2026-05-25: the canonical source for all dotfiles content (skills, zshrc, tmux.conf, gitconfig template, claude/settings, iterm2 keys, MCP user-mcp.json) moves into `marlinjai/bootstrap` as module-local files. Each module holds the files it installs (`modules/claude-skills/skills/*`, `modules/zsh-baseline/zshrc`, etc.). The `~/software-dev/dotfiles` repo is archived (not deleted; git history stays viewable) as the final step of Phase 3 once `--profile marlin-dev --reconcile` confirms zero drift against Marlin's current laptop state. Marlin retains a personal `~/.bootstrap-overrides.local` (gitignored, per-machine) for genuinely laptop-specific overrides like iTerm2 plist deltas or `claude/settings.local.json` rules.

## Risks

- **Bootstrap repo drift during migration.** While the unified repo is being built, every change to Lola-Stories/bootstrap or dotfiles/install.sh has to be made in both places, or the migration target diverges from production. Mitigation: freeze direct edits to the legacy scripts during Phase 2 + 3; route fixes through the unified repo and re-curl the wrapper.
- **Validating marlin-dev against Marlin's actual laptop.** Marlin's current state is the integral of many ad-hoc decisions over months. A clean-room run might surface gaps. Mitigation: the `--reconcile` mode in Phase 3 lists deltas without applying them; we treat the first run as a diff session, not a replacement.
- **Infisical login is interactive.** Browser auth breaks the "unattended 25-min" promise. Mitigation: prompt for login at the start, alongside identity prompts, so all interactive bits happen in the first 60 seconds.
- **Personal-data leakage from dotfiles into non-Marlin profiles.** Marlin's current dotfiles include hardcoded personal data (`gitconfig` with literal name/email, possibly hardcoded `$HOME/software-dev/*` paths in `zshrc`, MCP server env vars with personal API key names). Any dotfiles content reused by a non-Marlin user must be templated or scrubbed first. Mitigation: Phase 3 starts with an audit pass that classifies every file in dotfiles as `personal-literal` (never propagate), `personal-templated` (template + prompt), or `universal` (symlink as-is). The `marlin-dev` profile is allowed to symlink universal files only; everything personal goes through the template path. Even a "Marlin sets up his own mac-mini" run does not regress this rule, because identity is cached in `~/.bootstrap-identity.local` and templating re-renders deterministically.
- **Dotfiles archive cutover.** Resolved 2026-05-25 (see Open question 4): dotfiles is absorbed into bootstrap and archived at the end of Phase 3. The risk during migration is that Marlin pushes a fix to dotfiles after Phase 2 lands and before Phase 3 archives it, creating divergence. Mitigation: freeze dotfiles direct edits at the start of Phase 3 (announce in repo README + ROADMAP); the freeze stays for the few days needed to land the migration. Marlin's `~/.bootstrap-overrides.local` covers any urgent per-machine fix during the freeze without unfreezing the repo.

## Cross-references

- Handover that started this work: `docs/handovers/2026-05-25-tooling-baseline-bootstrap.md`
- Orchestrator README and pyproject already reference `github.com/marlinjai/orchestrator` (no URL changes needed once the push completes).
- Lola/bootstrap source: https://github.com/Lola-Stories/bootstrap
- Dotfiles install.sh: `~/software-dev/dotfiles/install.sh`
- Infisical reference: `~/.claude/projects/-Users-marlinjai/memory/reference_infisical_plan.md` (referenced from global CLAUDE.md)
