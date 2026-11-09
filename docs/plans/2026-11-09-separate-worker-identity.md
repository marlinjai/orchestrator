---
type: plan
status: draft
date: 2026-11-09
title: "A separate identity for orchestrator Workers: a per-task container in a dedicated, home-less Colima VM"
summary: >
  Today a Worker runs as Marlin's macOS user, and on the Claude path no in-process sandbox keeps it from his keychain.
  This plan runs every Worker in a throwaway container inside a dedicated Colima VM that mounts nothing of Marlin's
  home, cannot reach the Mac's localhost, the tailnet or private networks, and never holds a credential: Claude
  requests go through a host-side proxy that adds the token. Results come back as a git bundle checked on the host,
  and no Worker-written code ever runs on the Mac. Revised after an independent review that verified Colima's default
  profile mounts Marlin's whole home writable into its VM.
---

# A separate identity for orchestrator Workers

## Why

The dependency security fleet (knowledge-base `docs/plans/2026-11-08-dependency-security-fleet.md`) found that a
Worker's only confinement never ran and that a Worker could write anywhere as Marlin. Pull request 44 adds a file-tool
hook, an operating-system sandbox for Bash, empty git and gh configuration and a keychain deny on the Mercury path. On
the Claude path the Claude Code sandbox cannot deny the macOS keychain daemon: a Worker can read keychain metadata and
trigger "wants to use your confidential information" dialogs (it happened on 2026-11-09 during probes). A boundary that
does not depend on Marlin clicking Deny needs a different identity with no keychain, no home and no credentials of his.

## Verified facts that shape the design (independent review, 2026-11-09, read-only)

- Colima's `default` profile has `mounts: []`, which Colima treats as "mount the home folder": the generated Lima
  config mounts `~` writable over virtiofs. Root inside that VM can read `~/.ssh`, `~/.config/gh`, Infisical files and
  write `~/.zshrc` (code execution on the Mac as Marlin at the next shell).
- Docker 28.4 in that VM runs runc with seccomp and AppArmor but no user-namespace remap; container root is VM root.
- The `default` VM runs 9 containers, including Marlin's development databases, reachable from the default bridge.
- The Docker socket (`~/.colima/default/docker.sock`, mode 0600, owner marlinjai) gives every process of Marlin's VM
  root, hence write access to his home through the mount.
- Lima `user-v2` networking maps `host.lima.internal` (192.168.5.2) to the Mac's localhost, where the automation
  Chrome's remote-debugging ports 9222 and 9224 listen (full control of a signed-in profile), plus other local
  services; the host routes the tailnet (100.64/10), so containers can reach hermes and the secrets proxy.
- `claude setup-token` (Claude Code documentation): a browser authorization by a logged-in claude.ai user, prints a
  one-year token to the terminal only, "can only make model requests", revocation not documented. In a container
  environment variable it would be readable in `/proc/1/environ` and in `docker inspect` on the host.
- Fetching from a local clone runs `git-upload-pack` as Marlin, which reads the clone's configuration and alternates.

## Options compared

| Option | Separation from Marlin's keychain, home, credentials | Verdict |
|---|---|---|
| 1. Second macOS user | Real (per-user keychain and home) | Possible, but switching users from a process needs privileged helpers and a separate GUI session; not chosen |
| 2. Container in a **dedicated, home-less** Colima VM, egress-filtered, credential-free | Real once the conditions below hold; nothing of Marlin's is mounted or reachable | **Recommended** |
| 3. Unprivileged user or rootful Docker on hermes | Hermes' Docker daemon runs as root; joining the `docker` group means root on a shared host beside the secrets proxy | Worse today; acceptable later only with rootless Docker or Podman under a dedicated user and the same egress rules |
| 4. macOS VM | Strong | Overkill |

## Design

1. **Dedicated Colima profile** `orch-worker`: its own VM, `mounts` listing only `~/.orchestrator/worker-clones`
   (writable) and nothing else of the home folder; Docker with `userns-remap` so container root is unprivileged in the
   VM; nothing else runs in this VM. The `default` profile is never used for Workers. The orchestrator refuses to start
   a Worker unless it can verify, from inside the VM, that `/Users/marlinjai` (other than the clones path) is absent.
2. **Egress filter in the VM** (`DOCKER-USER` chain or nftables): drop traffic to 192.168.5.0/24 (host.lima.internal),
   100.64.0.0/10 (tailnet), RFC 1918 ranges, link-local and the VM's own services; allow public internet for package
   installs; allow the Claude proxy (item 4) as the only path to Anthropic.
3. **Container per task run:** `--rm`, read-only root filesystem, `--cap-drop ALL`, `--security-opt
   no-new-privileges`, `--pids-limit`, memory and CPU limits, a size-capped tmpfs for `/tmp` and caches, a non-root
   user, image run by digest with `--pull=never`. Mounted: only the task's standalone clone at `/work`. No Docker
   socket, no SSH agent, no host paths.
4. **The Worker never holds a credential.** Claude requests go to a small proxy outside the container (a sidecar in the
   same VM, or on the host listening only on the VM-facing interface). The Worker sees `ANTHROPIC_BASE_URL=<proxy>`
   and a dummy `ANTHROPIC_AUTH_TOKEN`; the proxy replaces the auth, allows only the model-request endpoints, and holds
   the real token, read from Infisical at start through the piped pattern, never printed and never in a container's
   environment. To verify before building: that the Agent SDK honours `ANTHROPIC_BASE_URL`, that a dummy auth token
   outranks the subscription token as documented for Claude Code, and that Anthropic's Agent SDK terms allow this use
   of a subscription token for Marlin's own agents.
5. **No other credentials:** no `GH_TOKEN`, no git credentials, no Infisical identity, no secrets-proxy tool inside the
   container; the in-process layers of pull request 44 stay on as defence in depth. Goals that need real secrets are
   not run in this mode.
6. **Handback by bundle:** at the end the container runs `git bundle create /work/out.bundle <worker-branch>`. The host
   checks that `out.bundle` is a regular file (not a symlink) under a size cap, then, with a minimum git version
   pinned, runs `GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c transfer.fsckObjects=true fetch
   --no-tags --no-recurse-submodules --no-write-fetch-head <bundle> <branch>:refs/remotes/worker/<task>` with a
   timeout. The host never runs git with the clone as working directory, never fetches from the clone path, and never
   follows a path inside the clone (symlinks that dangle in the container resolve on the host).
7. **No Worker-written code runs on the Mac.** Reviews, tests and fixes of Worker branches run in the same container
   mode; land-pr's unattended fixer must not run on the host for these branches (pinned pull requests already get no
   fixer); a person or the orchestrator reviews the diff, and GitHub Actions runs on Worker branches are checked for
   which secrets they receive.
8. **State:** stays on the host; the Worker reports through `update_state`, served on the host side for the bound task
   only.

## Effects on worktree and tools

- Standalone clone instead of a linked worktree; the branch comes back as a bundle; merging stays on the host.
- Package caches live in the container's tmpfs or a per-task volume, so nothing writes to Marlin's home; first
  installs are slower.
- Bash, Write and Edit work inside `/work`; everything else is read-only or absent; no localhost services, tailnet or
  development databases are reachable.

## Proof (before Workers run again)

Every probe prints only case names and PASS/FAIL; credential probes discard output and report only an exit status;
no probe touches the macOS keychain.

1. From inside the `orch-worker` VM (not only the container): Marlin's home is absent except the clones path.
2. From a Worker container: writes outside `/work` and `/tmp` fail; the Docker socket, `~/.ssh`, `~/.config` are
   absent; 192.168.5.2 ports 9222, 9224 and other host ports, 100.64/10 (hermes, secrets proxy) and sibling
   containers are unreachable; public HTTPS works.
3. The Claude token is absent from the container environment and from `docker inspect` (checked by name and by a keyed
   fingerprint comparison, never by printing); model requests work through the proxy; other Anthropic endpoints are
   refused by the proxy.
4. No GitHub credentials: an authenticated `git ls-remote` against a private repository fails (exit status only).
5. Handback: canaries for a planted hook, `core.fsmonitor`, `.git/config`, `objects/info/alternates` and a symlink to
   a host path stay inert; after the fetch, `git fsck` passes and only `refs/remotes/worker/<task>` changed.
6. Controls: the same probes against today's in-host Worker and against the `default` profile show the escapes.

## Rollback

Opt-in flag (`--isolation container`) first, default only after the proofs pass; the in-host mode stays available only
with an explicit flag and a warning, and Workers stay stopped in the meantime. Removing the container mode is deleting
the flag path and the `orch-worker` profile; no data migration. Token revocation must be tested (where and how a
`setup-token` token is revoked) before the token is relied on; until then the proxy can simply stop using it.

## What needs Marlin

- Approve this plan.
- Authorize the Worker's Claude token once: `claude setup-token` needs his consent in a browser on his Claude account
  (genuine human authorization). He never sees or pastes the value: the orchestrator runs the command so that the
  printed token is captured into a variable and written straight to Infisical through the API via standard input,
  verified by a keyed fingerprint. Because the documentation offers no headless mode, the capture is tested first in a
  way that cannot print (output to a pipe only, the variable checked by length class).

## Done when

- [ ] Plan decided; the three open checks in item 4 verified.
- [ ] `orch-worker` profile, egress filter, container runner, Claude proxy, bundle handback implemented with tests.
- [ ] Proof list passes in a real run, with controls; token revocation path tested.
- [ ] Documentation and the security plan updated; the "do not run the orchestrator" memory note lifted only then.
