---
type: handover
status: draft
date: 2026-05-25
title: Tooling baseline bootstrap for new machines and co-op contributors
summary: Push orchestrator + sibling tooling repos to git, decide their hosting structure, and author a Lola Stories contributor-onboarding script that installs the full Marlin tooling baseline on a fresh machine.
---

# Handover prompt: tooling baseline bootstrap

Paste the section below into a fresh Claude Code session. The prompt is self-contained: it states the goal, lists the context, names the decisions to drive, and ends with what to ship.

---

```
# Goal

Set up a clean tooling baseline bootstrap so any new machine (Marlin's
laptop, mac-mini, or a Lola Stories co-op contributor's machine) can get
the full Marlin tooling stack with one script run. The pieces that need
to land together: orchestrator (autonomous Claude Code Worker + Decision
Proxy), trello-cli, printing-press, plus their matching Claude Code
skills.

# Context: what's already in place (from prior session, 2026-05-24)

- `~/software-dev/orchestrator` is at v0.2.0 (commit `f3ac8b2` on master,
  not pushed anywhere). 106 tests pass. Real dogfood validated. Plans +
  ROADMAP are up to date.
- `~/software-dev/dotfiles` already symlinks all skills from
  `dotfiles/claude/skills/*` into `~/.claude/skills/` via install.sh.
- `~/software-dev/dotfiles/claude/skills/autonomous-orchestration/SKILL.md`
  exists and is the playbook for using the orchestrator from Claude Code.
- `dotfiles/install.sh` was updated to `uv tool install --editable
  $HOME/software-dev/orchestrator` IF the repo exists locally, with a
  clone hint if not. The clone hint references
  `git@github.com:marlinjai/orchestrator` but that remote does not exist
  yet.
- `~/software-dev/lola-stories/scripts/setup-mac-mini.sh` is for
  deploying the landing page Mac Mini (Homebrew + Node + pm2 + Cloudflare
  tunnel). It is NOT a contributor onboarding script. Lola has no such
  script today.

# Context: what's NOT in place / unknown

- The orchestrator repo has no git remote. The other "Marlin tooling"
  repos (trello-cli, printing-press) are not at standard
  `~/software-dev/` paths on this machine. Their locations are unknown
  and might be re-homed.
- Marlin uses 3+ machines actively. Today only this laptop has the
  orchestrator and the autonomous-orchestration skill. Other machines
  need them via the bootstrap.

# Decisions to drive in this session

1. **Find the canonical home for each tooling repo.**
   - Where is `trello-cli` today? Check `~/software-dev/`, `~/Code/`,
     `~/dev/`, `~/Projects/`. If absent: is it on github already? Local
     only? Lost?
   - Same for `printing-press`. The `printing-press` skill in
     `~/.claude/skills/` references it, so it exists somewhere.
   - Ask Marlin if uncertain.

2. **Hosting decisions for each repo.**
   - Public on github.com/marlinjai? Private with deploy keys? An org
     (e.g. Lola-Stories org)?
   - Marlin's preference: he wants co-op contributors to be able to
     bootstrap their machines without his hand-holding. That implies
     public OR private + accessible to the Lola org.

3. **Where do the tool repos live in the bootstrap chain?**
   Three options, pick one:
   - **Option A: each as its own repo, cloned by the bootstrap.** The
     bootstrap script clones orchestrator, trello-cli, printing-press
     into `~/software-dev/` then installs each. Cleanest separation, but
     requires three remote repos.
   - **Option B: all under the dotfiles repo.** The tools live as
     subdirectories or submodules in dotfiles. One remote, but mixes
     personal-config and shareable-tooling concerns.
   - **Option C: all under a new `marlin-tooling` umbrella repo.** A
     single shareable repo holding all the tools. New repo to create,
     but clean conceptual boundary.

   Recommend Option A unless there's a strong reason otherwise. Submodules
   in dotfiles (Option B) are notoriously annoying. An umbrella repo
   (Option C) adds a layer of indirection nobody asked for.

4. **Where does the contributor bootstrap script live?**
   - `~/software-dev/lola-stories/scripts/bootstrap-contributor.sh` (a
     new script alongside the existing setup-mac-mini.sh) so a Lola
     co-op contributor clones lola-stories and runs the script
   - Or `~/software-dev/dotfiles/bootstrap-contributor.sh`? Cleaner if
     the dotfiles repo is meant to be cloneable by anyone, messier if
     dotfiles is personal config.
   - Recommend the Lola path: contributor onboarding belongs in the
     project they're joining, not in Marlin's personal dotfiles.

# What to ship in this session

1. **Push orchestrator to its chosen remote.** First commit is
   `f3ac8b2`. Use whatever GitHub URL Marlin picks. Update
   `pyproject.toml`, `README.md`, `dotfiles/install.sh`, and
   `dotfiles/claude/skills/autonomous-orchestration/SKILL.md` to
   reference the real URL (search/replace
   `github.com/marlinjai/orchestrator` with the chosen one).
2. **Same for trello-cli + printing-press.** Find them, push if needed,
   note their install commands.
3. **Author `~/software-dev/lola-stories/scripts/bootstrap-contributor.sh`.**
   It should:
   - Check for Homebrew + uv + claude-code CLI; install if missing
   - Clone (or pull) the three tool repos into `~/software-dev/`
   - Install each: orchestrator via `uv tool install --editable`,
     trello-cli + printing-press via whatever their conventions are
   - Clone Marlin's dotfiles (or skip if they're considered personal),
     OR symlink just the skills directory from each tool's repo into
     `~/.claude/skills/`
   - Verify by running `orchestrator --help`, `trello --help`, etc.
4. **Update three READMEs.** Each tool repo should mention that the
   contributor bootstrap exists and how to use it.
5. **Update orchestrator ROADMAP.md** to mark the "tooling baseline
   bootstrap" follow-up as complete, with the resolution.

# Constraints

- Do not push from this session unless Marlin confirms.
- Use Marlin's typography rules (no em-dashes, no en-dashes anywhere
  including commit messages). His CLAUDE.md is authoritative.
- Use Infisical for any secrets, never literal env vars.
- One conventional-commit per tool repo's URL change.
- Lola Stories contributor docs should be in clear "for a new
  contributor on their first day" voice, not assume Marlin-specific
  context.

# Verification before claiming done

Run on this machine (which already has everything):
- `which orchestrator trello` (or equivalent), all should resolve.
- `claude` → check that `autonomous-orchestration` shows in `/skills`.
- `bash -n` the new bootstrap script to confirm syntax.

A real cross-machine validation would require a second machine and is
out of scope for this session. Mark it as a follow-up.

# Report at the end

- The chosen hosting decisions (Option A/B/C, repo URLs, public/private)
- The four (or however many) commits across the repos
- The Lola contributor bootstrap script content (or its path so Marlin
  can review)
- Anything left blocked that needs Marlin's input
```

---

## Notes for future-self (the fresh session)

- The orchestrator session that ran 2026-05-24 left ROADMAP + CLAUDE.md + plans + the v0.2.0 release in a clean state. Read those first; they capture two production findings (`infisical run` collision with SDK auth; Worker discretionary state reporting) that informed real code changes.
- The `autonomous-orchestration` skill description has been tuned to trigger on the word "autonomous" and explicit dispatch verbs. If you find yourself wanting to invoke it during this bootstrap work, you probably shouldn't — this session is about distribution, not about dispatching a Worker.
- If `printing-press` and `trello-cli` turn out to be on github already under a Lola-Stories org or similar, the cross-tool URL update becomes search-and-replace; if they're laptop-only, factor in the push step.
