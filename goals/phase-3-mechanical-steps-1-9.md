---
task: phase-3-mechanical-steps-1-9
spec: ~/software-dev/marlinjai-bootstrap/docs/phase-3-classification.md
---

# Goal

Execute mechanical migration steps 1 through 9 from the locked Phase 3 classification contract. Stop before step 10. Do not touch the dotfiles repo. Do not archive anything.

## Read first

1. **Canonical contract:** `~/software-dev/marlinjai-bootstrap/docs/phase-3-classification.md` (committed at `4076101` on the bootstrap repo main). This is the authoritative classification + migration order. Every row in its tables is a locked decision: do not relitigate.
2. **Bootstrap repo structure:** `~/software-dev/marlinjai-bootstrap-orch-phase-3-mechanical/` (this worktree). Read the existing `bootstrap` entrypoint, `lib/registry.sh`, `lib/*.sh`, and `modules/*/manifest.yaml` to understand how new modules and the registry work.
3. **Migration source:** `~/software-dev/dotfiles/` (READ-ONLY in this task). Read every file you need to migrate, do not modify or commit anything there.
4. **The main plan:** `~/software-dev/orchestrator/docs/plans/2026-05-25-unified-marlinjai-bootstrap.md` for high-level context.

## Scope

Execute steps 1 through 9 of the migration order at the bottom of the classification doc, one commit per step. **Do NOT execute steps 10, 11, or 12** (reconcile, freeze, archive). Those are interactive gates that need Marlin in the loop.

### Step 1: feat(modules): add homebrew-mobile module

New module `modules/homebrew-mobile/` with `manifest.yaml` (profile_tags: `[]` since opt-in-only via `custom` mode, depends_on: `[homebrew]`, no secrets, no org-gate) + `install.sh` that runs `brew bundle install --file=$BOOTSTRAP_ROOT/modules/homebrew-mobile/Brewfile` + a `Brewfile` listing: cocoapods, flutter, ant, maven, openjdk@17, composer, php. Register in tests/registry.bats by adding the module to the expected count where relevant. The classification doc says this module is "opt-in (not in any default profile, only available via custom mode)".

### Step 2: feat(modules): split claude/settings.json into contributor/marlin variants

Read `~/software-dev/dotfiles/claude/settings.json`. Create `modules/claude-code-install/settings.contributor.json` and `modules/claude-code-install/settings.marlin.json` per the locked decision:

- Contributor: `skipDangerousModePermissionPrompt: false`, `autoMemoryEnabled: true`, `autoDreamEnabled: true`. Drop or null all hook lines that point to dotfiles paths. Strip all enabledPlugins, MCP allowlist entries, and personal-flavor allowlist entries that are clearly Marlin-only (e.g. `WebFetch(domain:*.tavily.com)`).
- Marlin: a copy of the current dotfiles settings.json verbatim, with `skipDangerousModePermissionPrompt: true` preserved as it is today. Hook paths can stay pointing at dotfiles for now (Step 6 / future revisits handle the path migration once dotfiles is archived).

Update the `claude-code-install` module's `install.sh` to install the right variant based on profile (`PROFILE` env var is exported by the bootstrap entrypoint). If profile is `lola-contributor` or `custom` install contributor; if profile is `marlin-dev` install marlin. Cover with a bats test.

### Step 3: feat(modules): migrate claude/skills/ contributor subset

Copy these skill directories from `~/software-dev/dotfiles/claude/skills/` into `modules/claude-skills-contributor/skills/`: `release`, `frontend-design`, `find-skills`, `excalidraw-diagram`, `nano-banana-2`, `product-evolution`, `remotion-best-practices`, `video-to-website`, `visualizations`, `prioritization-frameworks`, `firecrawl-scraper`, `skill-builder`, `autonomous-orchestration`.

For `release`: read SKILL.md and replace the `@marlinjai/clearify` example with a generic `@your-org/your-package` placeholder. Other contributor skills can be copied verbatim. The classification doc's "Where `personal-templated` is noted, the SKILL.md gets a small templating pass" guidance.

Update `modules/claude-skills-contributor/install.sh` to symlink the skills into `~/.claude/skills/` idempotently (use the existing `link_safely` helper in `lib/symlink.sh` if it fits; otherwise extend it).

The module already exists from Phase 2 as a stub. Promote it from `marlin-dev` only to `[lola-contributor, marlin-dev]` profile_tags so both profiles install the contributor skills.

### Step 4: feat(modules): migrate claude/skills/ marlin-only subset

Copy these skill directories from `~/software-dev/dotfiles/claude/skills/` into `modules/claude-skills-marlin/skills/`: `knowledge`, `youtube-transcript`, `google-workspace-cli`, `scaffold-project`, `lumitra-analytics`, `domain-name-brainstormer`.

The classification doc explicitly notes hardcoded marlin paths in these (knowledge -> localhost:3020, youtube-transcript -> "Marlins Obsidian", etc). Do NOT generalize them: they are intentionally marlin-only. Copy verbatim.

Update `modules/claude-skills-marlin/install.sh` to symlink these into `~/.claude/skills/` idempotently. The module already exists as a stub.

### Step 5: feat(modules): migrate claude/user-mcp.json to marlin-dev profile

Copy `~/software-dev/dotfiles/claude/user-mcp.json` to `modules/mcp-servers/user-mcp.json`. Replace `COOLIFY_BASE_URL: https://coolify.lumitra.co` with `COOLIFY_BASE_URL: ${COOLIFY_BASE_URL:-https://coolify.lumitra.co}` style templating where applicable (the bootstrap entrypoint runs under bash, you can use `envsubst` or sed at install time).

Update `modules/mcp-servers/install.sh` to register each server via `claude mcp add-json` (envsubst-expanded). Keep `profile_tags: [marlin-dev]` only. The classification doc says contributors get NO MCP servers in the contributor profile (they opt-in per-project). Do not change that. Do not add an mcp-servers-contributor module.

### Step 6: feat(modules): migrate zshrc + zsh_aliases.marlin (side-file pattern)

Read `~/software-dev/dotfiles/zshrc` and `~/software-dev/dotfiles/zsh_aliases`. The current `modules/zsh-baseline/zshrc` was partly ported in Phase 2.

- Update `modules/zsh-baseline/zshrc` to include the universal content from dotfiles zshrc. Guard the two Marlin-specific tails (the `source $HOME/software-dev/dotfiles/zsh_aliases` line and the `source ~/.infisical-auto.zsh` line) with `[[ -f ... ]] &&` so they are no-ops on non-Marlin machines.
- Add a `[[ -f $HOME/.zsh_aliases.marlin ]] && source $HOME/.zsh_aliases.marlin` line near the bottom so the marlin side-file is sourced when present.
- Create `modules/zsh-baseline-marlin/zsh_aliases.marlin` containing the full contents of dotfiles/zsh_aliases (Mac Mini hub aliases, trello alias with Infisical UUID, hostname `marlinjai@marlins-mac-mini`, etc.). This module is marlin-dev profile_tags only.
- Create the new `modules/zsh-baseline-marlin/` module with manifest.yaml (depends on `zsh-baseline`, profile_tags `[marlin-dev]`) and install.sh that symlinks `zsh_aliases.marlin` into `~/.zsh_aliases.marlin`.

### Step 7: feat(modules): migrate tmux.conf, iterm2 keys, .cursorignore

- Copy `~/software-dev/dotfiles/tmux.conf` to `modules/tmux-tpm/tmux.conf`. Update `modules/tmux-tpm/install.sh` to symlink it to `~/.tmux.conf`.
- Copy `~/software-dev/dotfiles/iterm2/custom-keys.json` to `modules/iterm2-keybindings/custom-keys.json`. Update `modules/iterm2-keybindings/install.sh` to apply the keybindings via `/usr/libexec/PlistBuddy` (port the logic from dotfiles install.sh lines that handle iTerm2).
- Copy `~/software-dev/dotfiles/templates/.cursorignore` (if it exists; if not, skip this sub-item) to `modules/dotfiles-symlinks/templates/.cursorignore`. The `dotfiles-symlinks` module is currently a stub; promote to a real module with manifest_tags `[marlin-dev]` and install.sh that copies the .cursorignore template into the user's home or current project as needed. If the dotfiles-symlinks scope is unclear, document the choice in `DECISIONS.md`.

### Step 8: feat(modules): migrate claude/scripts/cc.sh and hooks/ to marlin-only

Create a new `modules/claude-marlin-extras/` module (or extend `claude-skills-marlin`, your call - document the choice in DECISIONS.md):

- Copy `~/software-dev/dotfiles/claude/scripts/cc.sh` to its target location, install.sh symlinks it into `~/.claude/scripts/cc.sh`.
- Copy `~/software-dev/dotfiles/claude/hooks/on-session-stop.sh` similarly.
- Skip `claude/scripts/session-sweep.sh` and `test-session-end-hook.sh` (classified as stays-per-machine, no migration target).

Profile tag: `[marlin-dev]`. The marlin-only hook + script are tied to Marlin's localhost:3020 dashboard and have no value for contributors.

### Step 9: feat(bootstrap): add --reconcile flag implementation

Implement the `--reconcile` flag in the `bootstrap` entrypoint and underlying registry. Behavior:

- For each module in the resolved profile order, source the module's install.sh in a special mode where it reports what would change rather than changing it. The simplest implementation: each install.sh checks `RECONCILE_MODE=1` early and switches mode (e.g. instead of `ln -sfn $src $tgt`, do `if [[ ! -L "$tgt" || "$(readlink "$tgt")" != "$src" ]]; then echo "WOULD CHANGE: $tgt"; fi`). Add a `reconcile_check()` helper in `lib/symlink.sh` and `lib/brew.sh` that modules call instead of inline ln/install.
- Output format: one line per module header `[module:<name>]`, then per-action diff lines indented two spaces. End with a summary `RECONCILE: X drift entries across Y modules`.
- Exit 0 if zero drift; exit 1 if any drift entries found (so CI / wakeup checks can gate on it).
- Bats test: `tests/reconcile.bats` covers the helper functions with a temp HOME so it does not touch the user's real files.

This is the most involved step. If you find that backporting reconcile_check into every existing install.sh is too invasive, propose an alternative in DECISIONS.md (e.g. a side-channel modules/<name>/reconcile.sh that runs INSTEAD of install.sh under RECONCILE_MODE=1) and continue.

## Verification before declaring done

1. `make test` passes (shellcheck + bats), including any new tests added for steps 1, 2, 6, 8, 9.
2. `./bootstrap --profile lola-contributor --dry-run` lists every module in dep order, no errors.
3. `./bootstrap --profile marlin-dev --dry-run` lists every module including the new marlin-only ones (zsh-baseline-marlin, claude-marlin-extras or however you scoped it).
4. `./bootstrap --profile lola-contributor --reconcile` runs on the worktree without touching the user's files and prints reconcile output. Expect drift (Marlin's machine has dotfiles content already wired up via the OLD dotfiles install.sh, the new modules report drift). That is correct: the whole point of step 10 is for Marlin to compare and confirm.
5. `shellcheck` clean across all new install.sh and lib/ files.
6. No file in `~/software-dev/dotfiles/` has been modified or deleted. Verify with `cd ~/software-dev/dotfiles && git status` -> clean.
7. Branch `orchestrator/phase-3-mechanical` has 9 commits, one per step, conventional-commit format.

## Definition of done

- All 9 step commits land on this branch.
- All 6 verification checks pass.
- The 9 commits push to `origin` (the bootstrap repo) at `orchestrator/phase-3-mechanical` branch. Do NOT merge to main.
- A PR is opened against `marlinjai/bootstrap` main: `gh pr create --repo marlinjai/bootstrap --base main --head orchestrator/phase-3-mechanical --title "Phase 3 mechanical migration (steps 1-9)" --body <recap of what each commit does, link to docs/phase-3-classification.md, note that step 10 reconcile is the next gate>`. Not draft — ready for Marlin's review.
- The classification doc at `docs/phase-3-classification.md` is left untouched.

## Constraints

- Stay in this worktree (`~/software-dev/marlinjai-bootstrap-orch-phase-3-mechanical`). The worktree IS the bootstrap repo on a feature branch. You can edit any file in it.
- READ-ONLY access to `~/software-dev/dotfiles/`. Do not modify, delete, or commit anything there. Do not even create temp files there. Read the files via Read tool or `cat`; do not `cd` into dotfiles for git operations.
- Do NOT touch `~/software-dev/orchestrator/` (this is the orchestrator repo, not the bootstrap).
- Do NOT modify `~/.claude/`, `~/.gitconfig`, `~/.zshrc`, `~/.tmux.conf`, or any other dotfile in the user's actual HOME. Reconcile-mode test must use a temp HOME via bats.
- Do NOT run any of the new install.sh scripts against the user's real machine. Test only via bats with temp HOME.
- Do NOT execute step 10 (--reconcile pass against laptop), step 11 (freeze announcement in dotfiles), or step 12 (archive dotfiles repo). Those need Marlin in the loop.
- Do NOT delete the existing `~/software-dev/dotfiles/` directory or its repo. Even after this Phase 3 work, dotfiles remains intact until Marlin runs step 10 and step 12.
- Do NOT push to `marlinjai/bootstrap` main. Push the branch only. The PR review is the human gate.
- One conventional-commit per step. The 9 commits should each be reviewable in isolation.
- Use Marlin's typography rules: no em-dashes (U+2014), no en-dashes (U+2013) anywhere including commit messages, README updates, PR body.
- If a `personal-templated` file needs a templating decision you cannot make from the classification doc alone (e.g. should the SKILL.md example be removed entirely or kept as a generic placeholder), document the call in DECISIONS.md with reasoning, then proceed. Do not block on user input mid-run.

## Notes

- The classification doc is authoritative. If a decision in this goal file conflicts with the classification doc, the doc wins.
- Use `update_state(kind="commit")` after every git commit and `update_state(kind="file_touched")` for substantial module additions so the orchestrator's reconciler sees Worker self-reports, not just system-reconciled commits.
- Use `update_state(kind="decision")` for any non-obvious choice (e.g. "extended dotfiles-symlinks module rather than creating a new claude-marlin-extras module").
- The Worker's previous run in this repo (Phase 1 + 2) is a good reference. Look at `git log --oneline main..HEAD` once you check out, you should see the classification doc commit + nothing else on this branch (it just branched from main).
- This is Phase 3 STEPS 1-9 ONLY. Step 10 (reconcile pass against Marlin's laptop) and beyond are explicitly excluded.
