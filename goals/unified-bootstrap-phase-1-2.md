---
task: unified-bootstrap-phase-1-2
spec: ../orchestrator/docs/plans/2026-05-25-unified-marlinjai-bootstrap.md
---

# Goal

Implement Phase 1 and Phase 2 of the unified marlinjai/bootstrap plan in this worktree. Phase 1 = scaffold the repo with module loader + registry + `bootstrap` entrypoint. Phase 2 = port every step of `Lola-Stories/bootstrap/install.sh` into modules so `./bootstrap --profile lola-contributor --dry-run` prints the correct sequence and `./bootstrap --profile lola-contributor` produces the same install outcome as the current Lola script (minus actual execution: full execution is verified later, this run validates the structure).

Do NOT attempt Phase 3 (dotfiles absorption + archive). That phase requires `--reconcile` against Marlin's live laptop and is explicitly out of scope for autonomous execution.

## Read first

1. **Plan (full):** `~/software-dev/orchestrator/docs/plans/2026-05-25-unified-marlinjai-bootstrap.md`. The plan's "Target shape", "Modules" table, "Implementation phases" (Phase 1 and Phase 2 only), and "Open questions for Marlin" (resolutions 2, 3, 4) are authoritative. Phase 3 and beyond are out of scope.
2. **Source to port (Phase 2 input):** `Lola-Stories/bootstrap` on GitHub. Fetch full content of `install.sh`, `Brewfile`, `zshrc`, `gitconfig.template`, `README.md` via `gh api repos/Lola-Stories/bootstrap/contents/<file> --jq '.content' | base64 -d`. The script is the canonical behavior to preserve.
3. **Architecture references:** the orchestrator's `CLAUDE.md` if you need pattern guidance, but you are NOT modifying the orchestrator. You are building a separate repo.
4. **Org membership pattern:** the plan resolution for `lola-monorepo` + `trello-pp-cli` modules requires `gh api orgs/Lola-Stories/members/$GH_USER` (silent 404 = non-member). Wire this check into the module registry's profile resolver.

## Scope

### Phase 1 deliverables (scaffold)

- `bootstrap` (bash entrypoint, executable) at repo root. Flags: `--profile <name>`, `--dry-run`, `--reconcile` (Phase 1 stub: print "not yet implemented" and exit 0), `--help`.
- `modules/` directory with one subdirectory per module declared in the plan's module table. Each contains:
  - `manifest.yaml` with fields: `name`, `description`, `profile_tags` (array), `depends_on` (array of module names, possibly empty), `requires_secrets` (array, possibly empty), `org_gated` (string or null), `est_duration_sec` (integer)
  - `install.sh` (Phase 1: stub that echoes `[module:<name>] would install` and exits 0; Phase 2 fills these in for modules included in `lola-contributor`)
  - Optional `verify.sh` (Phase 1: not required)
- Module loader: a bash function (in `lib/registry.sh` or similar) that globs `modules/*/manifest.yaml`, parses each, resolves dependencies in topological order, returns the ordered list of modules for a given profile.
- Profile definitions: derive profile membership from each module's `profile_tags` array (no separate profile config file needed). Profile names: `lola-contributor`, `marlin-dev`, `custom`. Mention `marlin-dev` profile in code but the modules tagged `marlin-dev` stay empty stubs in this run (Phase 3 fills them).
- Org-gating: in the profile resolver, if a module has `org_gated: <org>`, check `gh api orgs/<org>/members/$GH_USER 2>/dev/null` (silent 404 = non-member). Non-members: in `lola-contributor` profile fail-fast with a clear error message before any module runs; in `custom` profile silently hide the module from the picker.
- Identity caching: after `identity-prompts` module collects FULL_NAME / EMAIL / GH_USER, write to `~/.bootstrap-identity.local` (chmod 600). On re-runs, prompt with cached values as defaults.
- `--dry-run` mode: print `[module:<name>]` for each module in resolved order, do not execute any `install.sh`.
- `lib/` utilities: helper functions for prompting, idempotent symlink creation, logging with module-tagged prefix, sudo keep-alive (port from Lola/bootstrap), brew install wrapper.
- `tests/` with shellcheck + bats (bash automated testing system) tests covering: registry parsing, dependency resolution (cycle detection, missing dep error), profile membership, org-gating logic, dry-run output.
- `README.md` documenting profiles, how to run, how to add a module, the module manifest schema. Replace the temporary one-paragraph README that exists at HEAD.
- `.gitignore` covering `~/.bootstrap-identity.local`-style files, `.DS_Store`, editor swaps.
- `Makefile` or simple shell aliases: `make test` runs shellcheck + bats; `make lint` runs shellcheck only.

### Phase 2 deliverables (lola-contributor port)

For every step in `Lola-Stories/bootstrap/install.sh`, fill in the matching module's `install.sh` so it reproduces the behavior. Reference the plan's module table for the mapping. In particular:

- `xcode-clt` module: port the `xcode-select -p` gate and install trigger.
- `homebrew` module: port the `which brew` check and install one-liner.
- `homebrew-lean` module: include the existing Lola `Brewfile` content as `modules/homebrew-lean/Brewfile` (copy verbatim from Lola/bootstrap), run `brew bundle install --file=$BREWFILE`.
- `identity-prompts` module: prompt for FULL_NAME, EMAIL, GH_USER; cache to `~/.bootstrap-identity.local`.
- `gitconfig-template` module: include `modules/gitconfig-template/gitconfig.template` (copy from Lola/bootstrap), render with identity values, install at `~/.gitconfig` (idempotent: refuse to overwrite an existing non-template gitconfig without `--force`).
- `ssh-key-upload` module: port the ed25519 generation + `gh ssh-key add` flow.
- `zsh-baseline` module: port the starship + zsh plugin install + `modules/zsh-baseline/zshrc` symlink (copy zshrc verbatim from Lola/bootstrap; ensure the trello alias line is present).
- `claude-code-install` module: port the official Claude Code install one-liner.
- `colima-start` module: port the `colima start` if not running.
- `printing-press` module: port the printing-press generator install.
- `trello-pp-cli` module (`org_gated: Lola-Stories`): clone `Lola-Stories/trello-pp-cli` to `~/printing-press/library/trello/`, `go build` the binary. Ensure the zsh alias from `zsh-baseline` wraps it in `infisical run`.
- `lola-monorepo` module (`org_gated: Lola-Stories`): clone `Lola-Stories/lola-stories`, `pnpm install --frozen-lockfile`, `pnpm --filter=api prisma generate` (or whatever Lola/bootstrap does).
- `infisical-login` module: port the `infisical login --domain https://infisical.lumitra.co` flow. This module is mandatory across all profiles.

Modules tagged only `marlin-dev` (homebrew-fat, tmux-tpm, iterm2-keybindings, dotfiles-symlinks, claude-skills-marlin, mcp-servers, orchestrator-cli, vscode-extensions, gitconfig-marlin-literal): create the module directory with manifest.yaml + a stub install.sh that echoes "marlin-dev module, Phase 3". DO NOT implement them. The plan's resolved decision is that all profiles route through `gitconfig-template`; do NOT create a `gitconfig-marlin-literal` module.

### Verification before declaring done

1. `make test` passes (shellcheck + bats).
2. `./bootstrap --profile lola-contributor --dry-run` prints all `lola-contributor` modules in dependency-resolved order, no errors.
3. `./bootstrap --profile marlin-dev --dry-run` prints both contributor modules AND marlin-dev modules (stubs) in order, no errors.
4. `./bootstrap --profile custom --dry-run` prints "interactive mode unsupported in dry-run" and exits 0, OR shows an empty selection if non-interactive.
5. `./bootstrap --help` prints usage.
6. `shellcheck modules/*/install.sh bootstrap lib/*.sh` clean.
7. The org-gated test: simulate non-member by setting `GH_USER=nonexistentuser` and run `./bootstrap --profile lola-contributor --dry-run`. Expect a clear error message naming the missing org membership and exit non-zero.

### Phase 2 final deliverable: draft PR against Lola-Stories/bootstrap

After Phase 2 verification, prepare the 3-line wrapper that will replace `Lola-Stories/bootstrap/install.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/marlinjai/bootstrap/main/install.sh)" -- --profile lola-contributor "$@"
```

(Note: `marlinjai/bootstrap` uses `bootstrap` as the entrypoint, not `install.sh`. Adjust the curl URL accordingly, e.g. `https://raw.githubusercontent.com/marlinjai/bootstrap/main/bootstrap`.)

Open a DRAFT PR against `Lola-Stories/bootstrap` (default branch `main`) using `gh pr create --draft --repo Lola-Stories/bootstrap --base main --head <fork-or-branch>`. PR body: explain the migration, link to the plan at `https://github.com/marlinjai/orchestrator/blob/master/docs/plans/2026-05-25-unified-marlinjai-bootstrap.md`, list verification done. Do not merge.

If you do not have write access to fork or push a branch to Lola-Stories/bootstrap, instead write the proposed wrapper file + PR body content to `OUT/lola-wrapper-pr-draft.md` in this worktree and document this in the final summary so Marlin can open the PR manually.

## Definition of done

- All Phase 1 deliverables present and tested.
- All Phase 2 deliverables present and tested.
- `make test` passes.
- All seven verification checks above pass.
- One or more conventional-commit-style commits on this branch (`orchestrator/unified-bootstrap-phase-1-2`). Prefer one commit per phase (`feat(scaffold): module loader + entrypoint`, `feat(lola): port lola-contributor profile modules`) plus a final `docs: usage + module schema`.
- Draft PR opened against `Lola-Stories/bootstrap` (or `OUT/lola-wrapper-pr-draft.md` written with the content + clear note in final summary).
- Spec file at `~/software-dev/orchestrator/docs/plans/2026-05-25-unified-marlinjai-bootstrap.md` left untouched (do not flip its status; that is Marlin's call after review).

## Constraints

- Stay in this worktree (`~/software-dev/marlinjai-bootstrap-orch-unified-bootstrap-phase-1-2`). Do not modify files outside it. Specifically: do not edit `~/software-dev/dotfiles/`, `~/software-dev/bootstrap/` (the Lola clone), `~/software-dev/orchestrator/`, `~/software-dev/lola-stories/`, or `~/.claude/`.
- Do not push to `marlinjai/bootstrap` main. You may push your branch (`orchestrator/unified-bootstrap-phase-1-2`) to `origin` so the draft PR can reference a real commit, but do NOT push main, do NOT force-push.
- The draft PR against Lola-Stories/bootstrap is the only cross-repo action allowed. It must be `--draft`. Do not merge it.
- Use Marlin's typography rules in all output, commits, READMEs, and PR body: no em-dashes (U+2014), no en-dashes (U+2013). Hyphens inside compound words are fine.
- No `--no-verify`, no skipping hooks, no force pushes.
- No secrets in files. The `requires_secrets` field in manifests declares NAMES only; the actual secret values come from Infisical at runtime via `infisical run` wrappers.
- Do NOT actually run `brew install`, `git clone Lola-Stories/lola-stories`, `pnpm install`, or any other live install commands during this task. The install.sh scripts you write should DO these things when invoked, but you are not the invoker. Your job is to write and structure them, then verify via `--dry-run` and tests, not by full execution.
- Use `bats` for shell tests. If `bats` is not installed in the Worker environment, install it via `brew install bats-core` (this is a one-time tool install for the test framework, not a live install of the bootstrap modules).
- Do not invent profiles or modules not listed in the plan.
- Do not attempt Phase 3, even if time remains. If everything else is done early, polish tests, improve error messages, or add more dry-run output, but DO NOT touch `~/software-dev/dotfiles/`.

## Resumption note (2026-05-25, relaunch after 529 outage)

A previous Worker session under task-id `unified-bootstrap-phase-1-2` reached iteration 2 and built out the full scaffold + module ports before iteration 3 was interrupted by an Anthropic 529 outage. The work was preserved by the operator as a checkpoint commit in this worktree (see `git log`: `checkpoint: scaffolding + module ports built in Worker iter 2 (529-interrupted)`).

When you start, **read `git log` and inspect the existing files first**. Do not rewrite from scratch. The scaffold is already in HEAD: bootstrap entrypoint, lib/ utilities, 22 modules with manifest.yaml + install.sh, gitconfig template, Brewfile, zshrc, README, Makefile, DECISIONS.md, .gitignore, bats tests. Your remaining work:

1. Run `make test` (shellcheck + bats). Fix anything that fails.
2. Run the seven verification checks from the "Verification before declaring done" section above. Fix anything broken.
3. Audit the existing modules against the plan's module table for completeness (especially the `marlin-dev`-only stubs and the org-gating wiring).
4. Audit for typography violations (no em-dashes U+2014, no en-dashes U+2013 anywhere). Fix any found.
5. Commit your fixes with conventional-commit messages on the same branch (`orchestrator/unified-bootstrap-phase-1-2`).
6. Push the branch to `origin` (the bootstrap repo).
7. Open the draft PR against `Lola-Stories/bootstrap` as described in "Phase 2 final deliverable", or write `OUT/lola-wrapper-pr-draft.md` fallback if you lack write access.

The checkpoint commit author is `Marlin` (the operator), not you. Treat it as existing context, not as your own prior turn.

## Notes

- The plan's "Open questions for Marlin" point 1 (skills-contributor default-on vs opt-in) is unresolved. For this run, treat `claude-skills-contributor` as a stub module under `marlin-dev` only; do not include it in `lola-contributor`. Leave a comment in its manifest noting this is unresolved.
- If you discover the plan is missing a detail you need, do NOT update the plan. Make a reasonable decision, document it in your commit message or in a new `DECISIONS.md` file in the bootstrap repo, and continue.
- Worker should call `update_state(kind="commit")` after every git commit so the orchestrator sees commits as Worker-reported (decided_by=proxy) not reconciled-from-system. Same for `update_state(kind="file_touched")` for substantial file additions and `update_state(kind="decision")` for non-obvious choices (e.g. "chose bash over Python for the entrypoint because contributors should not need a Python interpreter present before `homebrew` module runs").
- If you cannot open the Lola draft PR (no write access, no fork, gh auth scope insufficient), write `OUT/lola-wrapper-pr-draft.md` with the exact wrapper content and PR body, then proceed. This is a recoverable fallback and counts as done.
- Definition of "interactive multi-select" for `custom` profile: a `fzf --multi` invocation backed by the registry. If fzf is not available, fall back to a numbered-list `read` loop. Phase 1 can stub this with a "not implemented" message if time is tight; Phase 2 should make it work at least for the basic case.
