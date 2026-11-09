# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security

- **A Worker could write anywhere on the machine; the worktree guard never ran.**
  `build_worktree_guard`, the check meant to keep a Worker inside its task
  worktree, was an SDK `can_use_tool` callback, which the SDK does not call for
  tools in `allowed_tools`, and `Write`, `Edit` and `Bash` are in the Worker's
  defaults. A Worker could therefore Write or Edit any path (including the repo's
  main checkout, the 2026-08-01 incident) and run any Bash command that writes
  anywhere, for example `echo > /elsewhere`, `cp`, `mv`, `tee` or `python -c`.
  The escape was reproduced with the real SDK on 0.2.93 and on 0.2.121.
  `NotebookEdit` was also unguarded (the check read only `file_path`).
  Fixed: a PreToolUse hook denies `Write`, `Edit`, `MultiEdit` and `NotebookEdit`
  outside the worktree and Bash runs in an OS sandbox (the Claude CLI's for the
  Claude Worker, a Seatbelt or bubblewrap profile of our own for the Mercury
  adapter's `run_command`) with writes limited to the worktree, its git metadata
  and temp dirs; the Worker is refused when no sandbox can run. A denied write
  also stops the turn. The file tools require an absolute, canonical path inside
  the worktree: a relative path, `~`, or a path through a symlink or `..` is
  refused (the tool resolves them against a base the hook cannot see, and a
  symlink can be re-pointed between check and write; a swap in that instant is a
  documented residual). Path resolution fails closed.
- **A linked worktree shares the main checkout's `.git`, and the sandbox let
  Bash write all of it** (an independent review reproduced `git update-ref
  refs/heads/main`, writing `packed-refs`, `HEAD`, `index` and `info/`).
  Chosen: a precise allow-list inside the shared `.git` (not a private clone: the
  deliverable branch lives in the shared repo, and operator-made worktrees
  passed with `--project` cannot be cloned). Only the Worker's own admin dir, its
  own branch ref and reflog, and the object store are writable; every other
  ref, `HEAD`, `index`, `packed-refs`, `info`, hooks, config and other worktrees
  are not, and `<work>/.git` cannot be rewritten. On macOS the Mercury profile
  makes the object store create-only (an existing object cannot be overwritten or
  deleted); on both macOS paths `objects/pack` and `objects/info` are not
  writable (a forged pack would shadow existing objects, `alternates` would
  repoint the store). On Linux the refs namespace directory and the object store
  are writable as a whole (bubblewrap binds directories), with `objects/pack` and
  `objects/info` read-only, and a worktree branch without a namespace (`feature`
  instead of `orchestrator/x`) is refused. Stated limits: the Claude CLI's
  sandbox takes deny lists only, so on the Claude path the deny list covers the
  refs and worktrees that exist when the Worker starts (refs and worktrees of a
  parallel Worker created later, and new branch names, are not covered) and an
  existing loose object can still be replaced; on every path a Worker can create
  NEW loose objects with any content (inert unless something references them,
  but a name it can predict is shadowed); the Worker's own admin dir, including
  its `HEAD`, is writable, so the orchestrator must not run git write operations
  in a Worker's worktree afterwards without checking `HEAD`. Git flows that no
  longer work inside the sandbox (the Worker is told): `git stash`, `tag`, new
  branches, `fetch`, `gc`/`pack-refs`/`repack`, `submodule`, `config --local`,
  `worktree add/prune`; commit, amend, rebase and detached HEAD still work.
- **UNRESOLVED on the Claude Worker path: a Worker's Bash can overwrite an
  existing loose object of the shared git object store.** The Claude CLI's
  sandbox takes deny lists only and cannot make the store create-only. Git does
  not verify an object's hash when it reads it normally, so a blob replaced under
  its existing name can later be checked out in the main checkout (or by any other
  worktree) with the attacker's content: a poisoning of the main checkout that no
  review of the Worker's own branch would show. Closed on the Mercury path on
  macOS (create-only) and for forged packs on both macOS paths; open on the Claude
  path (proved by `scripts/prove_confinement.py`, reported there as a known
  limit). Until a Worker runs under a separate OS identity (plan #45), Claude
  Workers must not be run against a repository whose main checkout matters.
- **Credentials.** Under its default routes the Worker holds no usable git or gh
  credentials: forge, cloud and registry tokens are removed from its environment,
  gh and git are pointed at empty configuration (no credential helper, no
  askpass, no prompt), credential files (`~/.ssh`, `~/.config/gh`, `~/.aws`,
  `~/.gitconfig`, ...) are unreadable, and `security`, `gh auth`, git credential
  commands are on the Bash denylist. This is not a boundary against an
  adversarial Worker on the Claude path (the denylist is a pattern list; the
  keychain daemon and the launchd-managed ssh-agent socket stay reachable
  there; the Mercury profile denies both). A read of a private repository with
  no credentials fails.
- **The orchestrator's Bash denylist now applies to the Claude Worker** (it was
  promised in the system prompt and never enforced; the unused `denied_bash`
  parameter is gone): `rm -rf`, `git reset --hard`, force push, `npm`/`pnpm
  publish`, `curl` to `api.*`, `gh pr` write actions, `terraform apply` and
  destructive SQL are refused for the Claude Worker as they already were for the
  Mercury adapter. `rm -rf node_modules` is among them. The Claude Worker's cwd
  is now the canonical (symlink-free) path of its worktree.
  **The macOS keychain is NOT isolated on the Claude Worker path:** the Claude
  CLI's sandbox cannot deny the keychain daemon, so keychain metadata is
  readable from the Worker's Bash and an access request reaches the user as a
  dialog. The Mercury profile denies the daemon (keychain tools hang instead of
  returning data). Full separation of a Worker from the user's keychain needs a
  separate macOS user or a keychain-less environment, not a sandbox.
- A goal file can add only known tools or tools of configured MCP servers to a
  Worker's `allowed_tools`; permission rules such as `Bash(git push:*)` are
  dropped.
- The OpenAI-compatible (Mercury) adapter's `run_command`, which was a plain
  `bash -c`, runs under the same write policy and is refused when no sandbox can
  run; on macOS LaunchServices and the keychain daemon are unreachable from it.
  Known limit: a hard link that already exists inside the worktree to a file
  outside it stays writable through the shell (the sandbox judges paths).
  `scripts/prove_confinement.py` is the real-SDK proof (53 cases with the
  credential case: the Claude Worker and the Mercury adapter, plus `--control`
  runs that remove each layer and show the escape).
  A command that writes a global cache outside the worktree (`~/.npm`, a pnpm
  store, `~/.cache`) now fails inside the sandbox by design.

### Changed

- `claude-agent-sdk` floor raised to 0.2.121 (the first release patched for the
  critical advisory, and the first the confinement was proved on).
- CI installs from `uv.lock` (`uv sync --frozen`) so it tests the versions that
  ship, instead of resolving fresh.

### Removed

- `build_worktree_guard` and the Worker's `can_use_tool` callback.
