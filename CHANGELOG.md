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
  Reproduced with the real SDK on 0.2.93 and 0.2.121. `NotebookEdit` was also
  unguarded (the check read only `file_path`).
  Fixed: a PreToolUse hook now denies `Write`, `Edit`, `MultiEdit` and
  `NotebookEdit` outside the worktree (symlinks and `..` resolved), and Bash runs
  in the Claude Code OS sandbox with writes limited to the worktree, its git
  metadata and temp dirs. `scripts/prove_confinement.py` is the real-SDK proof.
  A command that writes a global cache outside the worktree (`~/.npm`, a pnpm
  store, `~/.cache`) now fails inside the sandbox by design.
  The OpenAI-compatible (Mercury) adapter's `run_command` is not sandboxed.

### Changed

- CI installs from `uv.lock` (`uv sync --frozen`) so it tests the versions that
  ship, instead of resolving fresh.

### Removed

- `build_worktree_guard` and the Worker's `can_use_tool` callback.
