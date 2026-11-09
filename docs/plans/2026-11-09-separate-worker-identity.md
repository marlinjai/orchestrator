---
type: plan
status: decided
date: 2026-11-09
title: "A separate identity for orchestrator Workers: a per-task container in a dedicated, home-less Colima VM"
summary: >
  Today a Worker runs as Marlin's macOS user, and on the Claude path no in-process sandbox keeps it from his keychain.
  This plan runs every Worker in a throwaway container inside a dedicated Colima VM that mounts nothing of Marlin's
  home, cannot reach the Mac's localhost, the tailnet or private networks, and never holds a credential: Claude
  requests go through a host-side proxy that adds a revocable Console API key from a capped workspace. Results come back as a git bundle checked on the host,
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


## Synthetic lab results (2026-11-09, throwaway Colima profile, synthetic tokens only, profile deleted afterwards)

- **Proxy routing:** the Claude Code CLI 2.1.319 and the Python Agent SDK 0.2.121 both send to `ANTHROPIC_BASE_URL`; an
  auth token in the environment outranks a subscription token; the SDK honours the proxy with `ANTHROPIC_API_KEY` set to
  a run secret (two `POST /v1/messages?beta=true`, answered through a stub upstream). A tool shell inside the Worker
  cannot repoint the CLI, but can send any request to any host egress allows: the proxy allowlist and the egress filter
  are what bound abuse.
- **VM:** a dedicated profile mounting one temp folder has no `/Users` at all. Docker userns-remap works only with
  `features.containerd-snapshotter=false` (Docker 29 refuses otherwise); container root then maps to an unprivileged
  VM uid (100000), and the hardened container (read-only root, `--cap-drop ALL`, no-new-privileges, pids and memory
  limits) still runs the CLI end to end. Files written through the mount appear on the Mac owned by Marlin's uid.
- **Egress:** without a filter a container reached the Mac's ports 9222, 9224 and 22, the VM's sshd, the tailnet secrets
  proxy and the bridge gateway; with the filter (DOCKER-USER for routed traffic, INPUT for the VM itself, ip6tables
  FORWARD drop) all were blocked. An internal Docker network per task plus a forward proxy that allows CONNECT only to
  listed hosts blocked direct 443, port 53, DNS resolution and non-listed hosts while the registry worked. IPv6 blocked.
- **Port forwards:** Lima's default forwarded every VM listener and published container port to the Mac on all
  interfaces, reachable from the LAN; `portForwarder: none` in the profile removed them.
- **Task separation:** bind-mounting only the task directory isolates files; containers on the same default bridge
  reached each other (br_netfilter not loaded), so each task gets its own internal network.
- **Persistence:** a VM restart lost the iptables rules, br_netfilter and the userns setting (Colima regenerates
  `daemon.json`); the profile's `docker:` section plus a `provision` script that installs the egress script, a systemd
  unit bound to docker.service and a modules-load entry restored everything after restart. `colima start` switches the
  global Docker context, so the runner always passes an explicit context and restores it.
- **Handback:** with the plan's exact bundle commands, canaries for hooks, `core.fsmonitor`, `packObjectsHook`,
  `core.sshCommand`, `core.pager`, `core.hooksPath`, alternates, symlinks and a forged `main` all stayed inert, only the
  target ref changed and fsck was clean; a symlinked bundle and a 120 MB object were refused. Controls: a plain
  `git fetch` from the clone pulled an object that existed only in an alternates repository (host data leak), and
  `git status` inside the clone executed `core.fsmonitor` (host code execution).
- **Proxy abuse:** a synthetic proxy allowed only `POST /v1/messages` (with `?beta=true`) and refused a wrong or expired
  secret, missing credential, other methods, `count_tokens`, batches, files, models, traversal and encoded paths,
  absolute-URI and `CONNECT` requests, a 2.1 MiB body and requests over the rate limit; the upstream only ever saw the
  upstream key. Beyond endpoints, a messages request can carry `mcp_servers` and server-side tools (web search, web
  fetch, code execution) that make Anthropic reach arbitrary URLs, so the proxy also rejects those in the body.
- Exact commands: `docs/plans/assets/2026-11-09-isolation-lab-commands.md`.

## Options compared

| Option | Separation from Marlin's keychain, home, credentials | Verdict |
|---|---|---|
| 1. Second macOS user | Real (per-user keychain and home) | Possible, but switching users from a process needs privileged helpers and a separate GUI session; not chosen |
| 2. Container in a **dedicated, home-less** Colima VM, egress-filtered, credential-free | Real once the conditions below hold; nothing of Marlin's is mounted or reachable | **Recommended** |
| 3. Unprivileged user or rootful Docker on hermes | Hermes' Docker daemon runs as root; joining the `docker` group means root on a shared host beside the secrets proxy | Worse today; acceptable later only with rootless Docker or Podman under a dedicated user and the same egress rules |
| 4. macOS VM | Strong | Overkill |

## Design

0. **Pinned image:** digest-pinned base, lockfiles, and an explicitly pinned Claude Code CLI version (the
   orchestrator pins none today).
1. **Dedicated Colima profile** `orch-worker`: its own VM, `mounts` listing only `~/.orchestrator/worker-clones`
   (writable) and nothing else of the home folder; Docker with `userns-remap` so container root is unprivileged in the
   VM; nothing else runs in this VM. The `default` profile is never used for Workers. The orchestrator refuses to start
   a Worker unless it can verify, from inside the VM, that `/Users/marlinjai` (other than the clones path) is absent.
2. **Egress filter in the VM** (`DOCKER-USER` chain or nftables, IPv4 and IPv6, or IPv6 disabled): drop
   192.168.5.0/24 except the single Claude proxy port on 192.168.5.2 (item 4), 100.64.0.0/10 (tailnet), RFC 1918,
   link-local and the VM's own services. Containers get **no direct internet**: direct 443 and port 53 are dropped;
   outbound HTTPS goes only through a forward proxy in the VM that allows the Claude proxy and the package registries
   by hostname (npm, PyPI, crates as needed). Rules are re-applied and re-tested on every VM start; the runner refuses
   to start a Worker if the check fails. Lima's port forwarding is disabled (`portForwarder: none`). Each task runs on
   its own `--internal` Docker network with the forward proxy dual-homed. Persistence comes from the profile's
   `docker:` section (`userns-remap: default`, `features.containerd-snapshotter: false`) and a `provision` script that
   installs the egress rules as a systemd unit bound to docker.service plus `br_netfilter`; the runner always uses an
   explicit Docker context, never the global one.
3. **Container per task run:** `--rm`, read-only root filesystem, `--cap-drop ALL`, `--security-opt
   no-new-privileges`, `--pids-limit`, memory and CPU limits, a size-capped tmpfs for `/tmp` and caches, a non-root
   user, image run by digest with `--pull=never`. Mounted: only that task's own directory
   (`worker-clones/<task>`, owned by the remapped user id) at `/work`, never the whole clones folder, so one task cannot
   see another's clone; the runner refuses `--userns=host`. No Docker socket, no SSH agent, no host paths.
4. **The Worker never holds a credential; the proxy bounds what it can do.** A small proxy on the Mac listens on
   `127.0.0.1:<port>`; the VM reaches it as `192.168.5.2:<port>`, the only host port the filter allows. It holds an
   **Anthropic Console API key** from a dedicated Console workspace with a spend limit (documented auth for Agent SDK
   agents, revocable and rotatable at once), read from Infisical at start through the piped pattern, never printed and
   never inside the VM. The Worker sees `ANTHROPIC_BASE_URL=http://192.168.5.2:<port>` and `ANTHROPIC_API_KEY=<run
   secret>`, a random value minted per run that the proxy maps to one task and invalidates when the run ends. The proxy:
   allows only `POST /v1/messages` (and `/v1/messages/count_tokens` if the SDK uses it); refuses every other path and
   method, absolute-URI and `CONNECT` requests and any Worker-set Host; forwards only to a hard-coded
   `https://api.anthropic.com`; strips incoming auth and adds the real key; enforces an allowed model list, a
   `max_tokens` ceiling, a body-size cap (1 MiB), only the `anthropic-beta` values the SDK needs, and rejects bodies
   carrying `mcp_servers` or server-side tools (web search, web fetch, code execution); counts tokens from each
   response's `usage` against a per-run budget, caps request rate and concurrency, and stops the run on a breach. The
   workspace spend limit is the final backstop. `update_state` is served the same way, on its own allowed port with
   per-task authentication. Residual risk, stated: a container escape to VM root can rewrite the filter and reach the
   Mac's other localhost services (including the automation Chrome on 9222 and 9224); the VM is the real boundary.
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
9. **The VM is not trusted between runs:** image digests are checked on the host; the VM is recreated regularly; only
   the orchestrator uses `colima ssh` and the `orch-worker` Docker socket; the clones folder is excluded from Spotlight
   and Time Machine.

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
3. The Console API key is absent from the VM, the container environment and `docker inspect` (checked by name and
   by a keyed fingerprint comparison, never by printing); model requests work through the proxy with the run secret.
4. No GitHub credentials: an authenticated `git ls-remote` against a private repository fails (exit status only).
5. Handback: canaries for a planted hook, `core.fsmonitor`, `.git/config`, `objects/info/alternates` and a symlink to
   a host path stay inert; after the fetch, `git fsck` passes and only `refs/remotes/worker/<task>` changed.
6. Proxy: refused paths, methods, absolute-URI and `CONNECT`; every cap trips; a run secret is refused after its run
   ends; requests never reach a host other than the hard-coded upstream.
7. Egress: a non-listed HTTPS host, direct 443 and port 53, IPv6 and the host gateway's other ports are refused; the
   registries and the Claude proxy work; the rules are in place after a VM restart; no Lima port forward appears on the
   Mac's localhost; one task's container cannot see another task's clone.
8. Controls: the same probes against today's in-host Worker and against the `default` profile show the escapes.

## Rollback

Opt-in flag (`--isolation container`) first, default only after the proofs pass; the in-host mode stays available only
with an explicit flag and a warning, and Workers stay stopped in the meantime. Removing the container mode is deleting
the flag path and the `orch-worker` profile; no data migration. Revocation drill, tested before Workers run: revoke the key in the
Console; the proxy receives 401 and the run stops; rotate by creating a new key and updating Infisical.

## Decisions (Marlin, 2026-11-09)

- **Plan approved**, including the cost: Workers bill per token on a Console API key instead of using his
  subscription (the orchestrator chose the subscription on purpose to avoid API spend).
- **Spend limit: 75 USD per month** on the dedicated Console workspace `orchestrator-workers`. That limit is the
  final backstop behind the proxy's own caps.
- **Key handling: minted by the agent through the automation browser, never by hand and never printed.** A
  `dev-browser` script creates the workspace, sets the limit, creates one key named `orchestrator-worker`, and
  moves the value straight into Infisical inside the same script (project `Dotfiles`, which this repository's
  `.infisical.json` is bound to, environment `prod`, folder `/orchestrator-worker`, key
  `ORCH_WORKER_ANTHROPIC_API_KEY`; its own folder so no `infisical run` that reads the root folder ever injects it). The script never logs the value; it reports only a prefix class and a
  length check. Verification afterwards is functional (one minimal request through the secrets proxy answering 200),
  never by reading the value. This replaces the earlier "Marlin types it into the Infisical web interface" step.
- **GitHub-enforced review is not pursued**: no GitHub Pro. The head-pinned merge gate stays enforced by land-pr
  only, with the trust boundary stated in the security fleet plan (a compromised process running as Marlin can
  bypass it).
- Considered and not chosen: a `claude setup-token` subscription token (one-year life, model requests only,
  revocation not documented, and Consumer Terms 3.7 limit automated access to API keys unless otherwise explicitly
  permitted; the Agent SDK documentation names the API key as its auth).

## Parked (Marlin, 2026-11-09)

The orchestrator has not run since 2026-10-02 and is not in use, so the build waits until autonomous runs are wanted
again. While parked, Workers do not run at all, which carries no risk. The ROADMAP line holds the item; the Console key
stays in Infisical unused (no cost) and expires 2027-02-09.

## Done when

- [x] Key minted 2026-11-09: workspace `orchestrator-workers` (`wrkspc_017ZKdAQ7Vatft7khZZDi4ja`), limit 75 USD per
  month confirmed after a reload, one key `orchestrator-worker` expiring 2027-02-09, stored as above, verified by one
  `max_tokens: 1` request through the secrets proxy answering 200 (value never printed). Rotate before 2027-02-09.
- [x] Plan decided (2026-11-09); the synthetic lab confirms the SDK honours `ANTHROPIC_BASE_URL` with the run secret.
- [ ] `orch-worker` profile, egress filter, container runner, Claude proxy, bundle handback implemented with tests.
- [ ] Proof list passes in a real run, with controls; the revocation drill passes.
- [ ] Documentation and the security plan updated; the "do not run the orchestrator" memory note lifted only then.
