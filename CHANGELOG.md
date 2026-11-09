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
  The escape was reproduced with the real SDK on 0.2.93 and on 0.2.121. `NotebookEdit` was also
  unguarded (the check read only `file_path`).
  Fixed: a PreToolUse hook now denies `Write`, `Edit`, `MultiEdit` and
  `NotebookEdit` outside the worktree (symlinks and `..` resolved), and Bash runs
  in the Claude Code OS sandbox with writes limited to the worktree, its git
  metadata and temp dirs (and refuses to run unconfined if the sandbox cannot
  start). A denied write also stops the turn, as the old guard intended. The file
  tools now require an absolute path inside the worktree: a relative path or `~`
  is refused, because the tool resolves it against a base the hook cannot see.
  `scripts/prove_confinement.py` is the real-SDK proof (27 cases: the
  Claude Worker on the SDK in `uv.lock` and the Mercury adapter's `run_command`,
  plus `--control` runs that remove each layer and show the escape).
  A command that writes a global cache outside the worktree (`~/.npm`, a pnpm
  store, `~/.cache`) now fails inside the sandbox by design.
  The OpenAI-compatible (Mercury) adapter's `run_command`, which was a plain
  `bash -c`, now runs under the same write policy (Seatbelt on macOS, bubblewrap
  on Linux) and is refused when no sandbox can run. Known limit: a hard link
  that already exists inside the worktree to a file outside it stays writable
  through the shell (the sandbox judges paths; the hook refuses the file tools
  on such a file).

### Changed

- `claude-agent-sdk` floor raised to 0.2.121 (the first release patched for the
  critical advisory, and the first the confinement was proved on).
- CI installs from `uv.lock` (`uv sync --frozen`) so it tests the versions that
  ship, instead of resolving fresh.

### Removed

- `build_worktree_guard` and the Worker's `can_use_tool` callback.
