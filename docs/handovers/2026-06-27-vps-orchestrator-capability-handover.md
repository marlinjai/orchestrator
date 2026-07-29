---
type: handover
title: "Install the orchestrator as a verified-execution capability on hermes (for the Agent OS / Paperclip swarm)"
date: 2026-06-27
summary: >
  Self-contained brief for a Claude Code session running ON hermes (srv843350). Installs the
  orchestrator CLI on the box, stands up an agent-proof trust anchor + a held-out vault, drops in a
  CLI playbook adapted for non-Claude agents (Paperclip / Hermes), and proves one swarm-agent ->
  verified-orchestrator-run -> draft-PR loop. The orchestrator is NOT a competing board or swarm: it
  is the trust/verify gate the existing swarm calls when it needs to LAND CODE that can be merged.
tags: [orchestrator, hermes, agent-os, paperclip, verified-execution, handover]
projects: [orchestrator]
---

# Handover: the orchestrator as a verified-execution capability on hermes

## How to use this
You are a Claude Code session running ON hermes (`srv843350`, root, `~ = /root`). Marlin fed you this
doc. Execute the steps IN ORDER. STOP and report at each checkpoint marked **[CHECKPOINT]**. Do not
skip the constraints in section 1. If anything is ambiguous or a step needs a decision Marlin has not
made, STOP and ask him rather than guessing.

## 0. Why this exists (the decision behind it)
hermes already runs the swarm and the boards: **Agent OS / Jarvis** (`:3737`), **Paperclip** (agent
orchestration board, loopback `:3100`), **Hermes** (agent CLI + gateway), and the **claude-session
dashboard** (`:3020`). Those are the breadth layer: launching and tracking many agents.

The **orchestrator** is a different thing and must NOT duplicate them. It is a verification-and-governance
harness: it runs a Claude Code Worker under a Decision Proxy, gates "done" on a `verify` command + a
**held-out verifier the agent cannot reach**, detects test-tampering and reward-hacking, and ends every
run at a **draft PR**. Its only job is to make a green checkmark trustworthy enough to merge.

So we are installing the orchestrator CLI here as a CAPABILITY the swarm calls: when a Paperclip / Hermes
/ Claude agent needs to land code that should be merge-ready, it routes that work through `orchestrator`
instead of editing the repo raw. The swarm stays the front end; the orchestrator is the trusted backend
for code-landing. We are NOT building another board or another swarm.

## 1. Hard constraints (do not violate)
- **Two human gates: DISPATCH and MERGE.** The terminal artifact of any run is a **draft PR**. NEVER
  merge into a product/revenue repo. NEVER push to a default branch.
- **Stakes gate is sacred.** A repo at `stakes_tier >= 3` makes the orchestrator refuse to start. NEVER
  pass `--confirm-stakes` or set `ORCHESTRATOR_CONFIRM_STAKES` on your own judgment. If a dispatch is
  refused, STOP and tell Marlin; only he authorizes a tier-3+ run, in chat, per repo.
- **Secrets never enter your context.** This box has plaintext keys in `/root/.agentic-os/config.json`
  and `/root/.bash_history`. NEVER `cat` them or any `.env`. The orchestrator Worker runs on the Claude
  subscription (it scrubs `ANTHROPIC_API_KEY`); do NOT inject provider API keys into its env. When a
  command could print a secret, do not run it here; route it through the secrets proxy or tell Marlin.
- **RAM reality: hermes is ~8 GB and already swaps.** Each orchestrator Worker is a full Claude Code SDK
  session (~300-800 MB + a repo clone). Run the orchestrator **SERIALLY here: at most ONE Worker at a
  time**, with small caps (`--max-iterations 6 --max-hours 0.5 --max-tokens 2000000`). Parallel / heavy
  runs belong on the Mac or a big-RAM box, NOT on hermes. If you need a fleet, stop and tell Marlin.

## 2. Preflight [CHECKPOINT]
Run and report results (these are all safe, no secrets):
```
uname -a; nproc; free -h; df -h / | tail -1
which uv git gh claude; claude --version 2>/dev/null
gh auth status 2>&1 | grep -iE "logged in|account" || echo "gh: check auth"
```
You ARE a Claude Code session on this box, so `claude` is installed and authed on Marlin's subscription;
the Worker will inherit that. If `uv` or `gh` is missing, install `uv`
(`curl -LsSf https://astral.sh/uv/install.sh | sh`) and `gh` before proceeding. Report what is present.

## 3. Install the orchestrator CLI
```
uv tool install git+https://github.com/marlinjai/orchestrator
orchestrator --help | head -20
uv tool list | grep claude-code-orchestrator   # require version >= 0.3.0; if lower, `uv tool upgrade claude-code-orchestrator`
```
**[CHECKPOINT]** confirm the binary is on PATH and version >= 0.3.0.

## 4. The linchpin: an agent-proof trust anchor + held-out vault
This is the step that makes the whole model real. If a Worker (or a calling agent) can write the trust
config or the held-out tests, the verification is theater. The defense is OS ownership:

4a. **Run Workers as an unprivileged user, not root.** hermes already has `marlins-hermes`. Workers (and
ideally the calling swarm agents) run as `marlins-hermes`; the trust config + held-out vault are owned by
`root` and are READ-ONLY to `marlins-hermes`. That way the Worker can never edit the gate it is judged by.
(If running everything as root is unavoidable for the first proof, say so explicitly in your report and
flag that the held-out guarantee is ADVISORY until the unprivileged-runner split is in place. Do not
silently pretend it is enforced.)

4b. **Trust registry** at `~marlins-hermes/.config/orchestrator/repos.toml` (root-owned, `chmod 644`),
keyed by the REAL git remote of ONE low-stakes repo with a remote (pick a small, non-revenue repo; ask
Marlin if unsure). Example shape:
```
[repos."github.com/<owner>/<repo>"]
stakes_tier = 2
held_out_verify = "bash /opt/verifier-vault/<repo>/check.sh"
```
4c. **Held-out vault** at `/opt/verifier-vault/<repo>/` (root-owned, `chmod 755` dir, `444` files,
NOT writable by `marlins-hermes`). Put a real, small test there that exercises behaviour the in-tree
suite does not, so an in-tree-green + held-out-red genuinely flags a reward-hack.
**[CHECKPOINT]** show `ls -l` of the vault + the repos.toml (NOT any secret), and confirm `marlins-hermes`
cannot write either path (`sudo -u marlins-hermes touch /opt/verifier-vault/<repo>/x` must FAIL).

## 5. The non-Claude CLI playbook (for Paperclip / Hermes agents)
Claude agents can use the `autonomous-orchestration` skill directly. Paperclip / Hermes / codex / grok
agents cannot load a Claude skill, so they drive the CLI directly. Write the playbook below verbatim to
`/root/workspace/orchestrator-cli-playbook.md`, then register it where those agents get their system
prompt / docs (for Paperclip: attach it to the agent definition; for Hermes: add it to the relevant
profile's instructions). **[CHECKPOINT]** confirm the file exists and is wired into at least one agent.

--- BEGIN /root/workspace/orchestrator-cli-playbook.md ---
# Orchestrator CLI playbook (non-Claude agents): how to land code you can trust

You are an autonomous agent. When you need to LAND CODE that should be merge-ready, do NOT edit the repo
directly. Route it through the `orchestrator` CLI: it runs a guarded Worker + Decision Proxy loop and
gates completion on a verify command plus an out-of-reach held-out verifier. Use it ONLY for a bounded
code change with a clear verify command. Not for research, exploration, or non-code work.

Steps:
1. Write a goal file `~/orchestrator-goals/<task-id>.md`:
   ---
   task: <task-id>
   verify: <a SCOPED test/build/lint command>
   ---
   # Goal
   <one paragraph: what to change + definition of done + constraints: stay in the worktree, do not push,
   additive/soft changes only>
   SCOPE the verify to mocked/unit tests that run in a bare environment. NEVER use a whole-suite command
   that needs Docker, a live DB, or a container runtime the gate cannot reach; it will fail for the
   environment, not the work.
2. Make an isolated checkout: `git -C <repo> worktree add -b orchestrator/<task-id> <wt> origin/main`,
   then install deps in `<wt>`.
3. Dispatch SERIALLY (one Worker at a time on this box), tight caps:
   `orchestrator start --goal ~/orchestrator-goals/<task-id>.md --project <wt> --task-id <task-id> --max-iterations 6 --max-hours 0.5 --max-tokens 2000000`
4. Poll: `orchestrator status --task-id <task-id>` (status: running|completed|escalated|stopped|failed).
5. On `completed`: the work is verify-green AND held-out-green. Open a DRAFT PR
   (`gh pr create --draft --base main`) and report the PR link. On `escalated`: read `exit_reason`; do
   NOT merge; surface it to Marlin. An `escalated` run whose held-out FAILED while the in-tree verify
   passed is a REWARD-HACK fingerprint; never retry it, never merge it.

Hard rules:
- NEVER pass `--confirm-stakes`. If a dispatch is refused by the stakes gate, STOP and tell Marlin; only
  he authorizes a tier-3+ repo.
- NEVER print secrets. Your context flows to third-party model hosts. Do not echo `.env`, `config.json`,
  credentials, or `run.log` lines that contain them. The orchestrator scrubs the Worker's env; you must
  not undo that by printing keys.
- NEVER edit `repos.toml` or the held-out vault. They are operator-owned; touching them voids the trust.
- Terminal artifact is a DRAFT PR. Never merge, never push a default branch.
- One Worker at a time on hermes (RAM). For parallel work, ask Marlin to run it on a bigger host.
--- END /root/workspace/orchestrator-cli-playbook.md ---

## 6. Prove one loop end to end [CHECKPOINT]
Pick ONE swarm agent (a Paperclip agent, or a Hermes profile) and have it run the playbook on the
low-stakes repo from step 4 with a tiny real change (e.g. a small bug fix or a doc/typecheck-level
change) that has a genuine verify gate. Drive it serially. Expected: the run reaches `completed`
(or `escalated` with a clear reason), and a DRAFT PR is opened. Report: the task-id, the final
`orchestrator status` (status + last_verify + last_held_out + tamper_paths), and the draft PR link.
This proves: swarm agent -> verified orchestrator run -> trustworthy draft PR, on the existing stack,
with no new UI.

## 7. Guards to leave in place
- Fleet kill: `touch ~/.orchestrator/GLOBAL_STOP` halts every run at the next iteration boundary.
- Per-task kill: `touch ~/.orchestrator/tasks/<id>/STOP`.
- Daily ceiling: set `ORCHESTRATOR_DAILY_TOKEN_CAP` (export in the runner's env) so the swarm cannot run
  away on the subscription. Keep runs serial on this box.

## 8. Report back to Marlin
A short summary: preflight results, CLI version installed, the trust-anchor + vault paths (and whether
the unprivileged-runner isolation is enforced or still advisory), the playbook path + which agent it is
wired into, and the proof-loop result (task-id, status, draft PR link). Flag anything that needed a
decision you deferred to him.

## Notes / known caveats
- hermes RAM is the binding constraint: this box is for serial verified-landing + the board, not a Worker
  fleet. The execution-vs-board split is intentional (board here, heavy execution on the Mac / a big box).
- The held-out guarantee is only as strong as the OS isolation in step 4. Do not overstate it.
- The orchestrator's bundled `autonomous-orchestration` skill (in the repo at
  `skills/autonomous-orchestration/SKILL.md`) is the Claude-Code driver; this playbook is its CLI-only
  twin for non-Claude agents. Keep them in sync if the CLI surface changes.
