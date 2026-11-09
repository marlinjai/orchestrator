---
title: Isolation lab commands (synthetic, 2026-11-09)
type: documentation
date: 2026-11-09
---

> Reconstructed after the lab from what was run (the lab scripts were deleted at cleanup); these commands were
> not re-executed after writing. Treat them as a recipe to re-verify, not as a tested script.

# Isolation lab: the commands that worked (2026-11-09)

Everything here is synthetic. No real credential was used or created. Placeholders:

- `<LABTMP>`: the temp directory mounted into the VM (`mktemp -d /tmp/orch-lab-mount.XXXXXX`, resolved with `pwd -P`).
- `<DUMMY_AUTH>`, `<FAKE_OAT>`: synthetic strings, `dummy-auth-$(openssl rand -hex 8)` and `fake-oat-$(openssl rand -hex 8)`.
- `<RUN_SECRET>`, `<EXPIRED_SECRET>`, `<FAKE_UPSTREAM_KEY>`: synthetic strings from `openssl rand -hex 12` with a prefix (E6).
- `dl`: a wrapper that pins the docker context so nothing can hit Colima's default profile:

```bash
printf '#!/bin/bash\nexec docker --context colima-orch-lab "$@"\n' > /tmp/orch-lab-work/dl && chmod +x /tmp/orch-lab-work/dl
```

Notes that apply to every case:

- `colima start orch-lab` switches the GLOBAL docker context to `colima-orch-lab`. Restore it right after every start and stop:
  `docker context use colima`. Use `dl` (explicit context) for everything in the lab.
- Run multi-word shell helpers in `bash`, not zsh (zsh does not word-split `$VAR` the way the commands below expect).
- Tested versions: Claude Code CLI 2.1.319, `claude-agent-sdk` 0.2.121 (the orchestrator pins no CLI version; its `uv.lock` locks the SDK), Docker 29.5.2 in the VM, git 2.56.0 on the Mac, Colima 0.10.3.

## 0. The VM and the test image

```bash
LABTMP=$(cd "$(mktemp -d /tmp/orch-lab-mount.XXXXXX)" && pwd -P); echo "$LABTMP" > /tmp/orch-lab-tmp.txt
colima start orch-lab --cpu 2 --memory 2 --disk 20 --runtime docker --mount "$LABTMP:w"
docker context use colima          # restore the global context Colima just switched
colima list                        # default and orch-lab, default untouched
```

Test image (`/tmp/orch-lab-work/image/Dockerfile`), built with `dl build -t orch-lab-claude:test .`:

```dockerfile
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates curl iproute2 netcat-openbsd procps \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@2.1.319 && npm cache clean --force
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir claude-agent-sdk==0.2.121
ENV PATH=/opt/venv/bin:$PATH
USER node
```

Git image for case C (`dl build -t orch-lab-git:test .`):

```dockerfile
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
USER node
```

The lab files below are copied into `<LABTMP>/lab/` (the only host path the VM sees) and bound into containers with
`-v <LABTMP>/lab:/lab:ro`.

## A. Precedence and base URL (inside containers on orch-lab)

### Synthetic test server `/lab/server.mjs` (never logs header values)

```js
// Synthetic Anthropic-like test server. NEVER logs header values: it only compares the Authorization / x-api-key
// values with the known synthetic strings held in env and prints which one matched.
import http from 'node:http';
const DUMMY = process.env.LAB_DUMMY_AUTH ?? '';
const OAT = process.env.LAB_FAKE_OAT ?? '';
const PORT = Number(process.env.LAB_PORT ?? 18080);
function classify(v) {
  if (!v) return 'NONE';
  const bare = v.replace(/^Bearer\s+/i, '');
  if (DUMMY && bare === DUMMY) return 'DUMMY_AUTH';
  if (OAT && bare === OAT) return 'FAKE_OAT';
  return 'OTHER';
}
const seen = [];
http.createServer((req, res) => {
  const auth = classify(req.headers['authorization']);
  const xkey = classify(req.headers['x-api-key']);
  const beta = String(req.headers['anthropic-beta'] ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  const line = { method: req.method, path: (req.url ?? '').split('?')[0], authorization: auth, x_api_key: xkey, beta_names: beta };
  console.log(JSON.stringify(line));
  seen.push(line);
  req.resume();
  req.on('end', () => {
    // A refusal is enough: the lab only asks which credential arrives, never needs a model answer.
    res.writeHead(401, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'lab server: synthetic refusal' } }));
  });
}).listen(PORT, '127.0.0.1', () => console.log(JSON.stringify({ listening: PORT })));
```

### `/lab/run-cli.sh` (CLI against the in-container server) and `/lab/run-sdk.sh` (Python SDK)

```bash
#!/bin/bash
# run-cli.sh <case-name>
set -u
export HOME=/tmp/home; mkdir -p "$HOME"
node /lab/server.mjs > /tmp/server-$1.log 2>&1 &
SP=$!
sleep 1
timeout 45 claude -p "say hi" --max-turns 1 > /tmp/cli-$1.out 2>&1
echo "cli exit: $?"
sleep 1; kill $SP 2>/dev/null; wait $SP 2>/dev/null
echo "requests seen by the test server (values never logged):"
grep -v listening /tmp/server-$1.log | sort | uniq -c | sort -rn | head -12
```

```bash
#!/bin/bash
# run-sdk.sh <case-name>  (same, with the Python Agent SDK)
set -u
export HOME=/tmp/home; mkdir -p "$HOME"
node /lab/server.mjs > /tmp/server-$1.log 2>&1 &
SP=$!
sleep 1
timeout 60 python /lab/sdk_query.py > /tmp/sdk-$1.out 2>&1
echo "sdk exit: $? ($(tail -2 /tmp/sdk-$1.out | tr '\n' ' ' | cut -c1-100))"
sleep 1; kill $SP 2>/dev/null; wait $SP 2>/dev/null
echo "requests seen by the test server (values never logged):"
grep -v listening /tmp/server-$1.log | sort | uniq -c | sort -rn | head -12
```

```python
# /lab/sdk_query.py
import asyncio, os, sys
from claude_agent_sdk import query, ClaudeAgentOptions
async def main():
    n = 0
    try:
        async for _ in query(prompt="say hi", options=ClaudeAgentOptions(max_turns=1)):
            n += 1
    except Exception as e:  # the synthetic server refuses on purpose
        print("sdk ended:", type(e).__name__)
    print("messages:", n)
asyncio.run(main())
```

### A1, A2, A3 (run from the Mac, all inside a container with no home mount and no credentials)

```bash
LABTMP=$(cat /tmp/orch-lab-tmp.txt); DL=/tmp/orch-lab-work/dl
run() { name=$1; script=$2; shift 2; $DL run --rm --network bridge -v $LABTMP/lab:/lab:ro \
  -e LAB_DUMMY_AUTH="<DUMMY_AUTH>" -e LAB_FAKE_OAT="<FAKE_OAT>" -e ANTHROPIC_BASE_URL=http://127.0.0.1:18080 \
  "$@" orch-lab-claude:test /lab/$script $name; }
# A1 CLI, base URL + auth token + OAuth token     -> POST /v1/messages arrives as DUMMY_AUTH, x-api-key NONE
run a1 run-cli.sh -e ANTHROPIC_AUTH_TOKEN="<DUMMY_AUTH>" -e CLAUDE_CODE_OAUTH_TOKEN="<FAKE_OAT>"
# A2 Python SDK, same                               -> DUMMY_AUTH
run a2-sdk-both run-sdk.sh -e ANTHROPIC_AUTH_TOKEN="<DUMMY_AUTH>" -e CLAUDE_CODE_OAUTH_TOKEN="<FAKE_OAT>"
# A3 without ANTHROPIC_AUTH_TOKEN                   -> FAKE_OAT, beta names now include oauth-2025-04-20
run a3-cli run-cli.sh -e CLAUDE_CODE_OAUTH_TOKEN="<FAKE_OAT>"
run a3-sdk run-sdk.sh -e CLAUDE_CODE_OAUTH_TOKEN="<FAKE_OAT>"
```

### A4: can the agent redirect itself (synthetic server answers with a real Bash tool call)

`/lab/server-tooluse.mjs`:

```js
// Synthetic server that answers the FIRST streaming /v1/messages with a Bash tool_use and later ones with plain text.
// Never logs header values: classification words only.
import http from 'node:http';
const DUMMY = process.env.LAB_DUMMY_AUTH ?? '', OAT = process.env.LAB_FAKE_OAT ?? '';
const PORT = Number(process.env.LAB_PORT ?? 18080);
const CMD = process.env.LAB_TOOL_COMMAND ?? 'echo hi';
const cls = (v) => !v ? 'NONE' : ((b) => b === DUMMY ? 'DUMMY_AUTH' : b === OAT ? 'FAKE_OAT' : 'OTHER')(v.replace(/^Bearer\s+/i, ''));
let turns = 0;
const sse = (res, events) => { res.writeHead(200, { 'content-type': 'text/event-stream' }); for (const [e, d] of events) res.write(`event: ${e}\ndata: ${JSON.stringify(d)}\n\n`); res.end(); };
const head = { type: 'message_start', message: { id: 'msg_lab', type: 'message', role: 'assistant', model: 'claude-sonnet-4-5', content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 } } };
http.createServer((req, res) => {
  const path = (req.url ?? '').split('?')[0];
  console.log(JSON.stringify({ method: req.method, path, authorization: cls(req.headers['authorization']), x_api_key: cls(req.headers['x-api-key']) }));
  let body = ''; req.on('data', (c) => (body += c)); req.on('end', () => {
    if (req.method === 'POST' && path === '/v1/messages' && body.includes('"stream":true')) {
      turns++;
      if (turns === 1) {
        return sse(res, [['message_start', head],
          ['content_block_start', { type: 'content_block_start', index: 0, content_block: { type: 'tool_use', id: 'toolu_lab', name: 'Bash', input: {} } }],
          ['content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: JSON.stringify({ command: CMD, description: 'lab' }) } }],
          ['content_block_stop', { type: 'content_block_stop', index: 0 }],
          ['message_delta', { type: 'message_delta', delta: { stop_reason: 'tool_use', stop_sequence: null }, usage: { output_tokens: 5 } }],
          ['message_stop', { type: 'message_stop' }]]);
      }
      return sse(res, [['message_start', head],
        ['content_block_start', { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } }],
        ['content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: 'done' } }],
        ['content_block_stop', { type: 'content_block_stop', index: 0 }],
        ['message_delta', { type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: 2 } }],
        ['message_stop', { type: 'message_stop' }]]);
    }
    res.writeHead(404); res.end('{}');
  });
}).listen(PORT, '127.0.0.1', () => console.log(JSON.stringify({ listening: PORT })));
```

`/lab/run-a4.sh`, run with `-e ANTHROPIC_AUTH_TOKEN="<DUMMY_AUTH>"` (non-root container user, `--dangerously-skip-permissions` inside the container only):

```bash
#!/bin/bash
set -u
export HOME=/tmp/home; mkdir -p "$HOME"
export LAB_TOOL_COMMAND='export ANTHROPIC_BASE_URL=http://203.0.113.1:9; code=$(curl -s -m 8 -o /dev/null -w "%{http_code}" https://example.com); echo "tool shell curl to public https host: http $code" > /tmp/a4-result.txt; echo "tool shell sees its own exported ANTHROPIC_BASE_URL: yes" >> /tmp/a4-result.txt'
node /lab/server-tooluse.mjs > /tmp/server-a4.log 2>&1 &
SP=$!
sleep 1
cd /tmp && timeout 60 claude -p "run the lab command" --max-turns 3 --dangerously-skip-permissions > /tmp/cli-a4.out 2>&1
echo "cli exit: $?"
sleep 1; kill $SP 2>/dev/null; wait $SP 2>/dev/null
echo "--- what the tool shell did:"; cat /tmp/a4-result.txt 2>&1
echo "--- requests the test server saw (CLI own traffic; values never logged):"
grep -v listening /tmp/server-a4.log | sort | uniq -c | sort -rn | head -8
```

```bash
$DL run --rm --network bridge -v $LABTMP/lab:/lab:ro -e LAB_DUMMY_AUTH="<DUMMY_AUTH>" -e LAB_FAKE_OAT="<FAKE_OAT>" \
  -e ANTHROPIC_BASE_URL=http://127.0.0.1:18080 -e ANTHROPIC_AUTH_TOKEN="<DUMMY_AUTH>" orch-lab-claude:test /lab/run-a4.sh
# result: the tool shell reached a public https host (200); the CLI's own POSTs still went to the original base URL as DUMMY_AUTH
```

## B. The VM

### B1: home absent inside the VM

```bash
colima ssh -p orch-lab -- sh -c 'ls /Users 2>&1; ls /Users/marlinjai 2>&1; mount | grep -E "virtiofs|9p|sshfs|fuse" | sed "s/ type .*//"'
colima ssh -p orch-lab -- sh -c "echo canary > <LABTMP>/from-vm.txt && echo write-ok"     # the only writable host mount
```

### B2: userns-remap (the three config facts that matter)

```bash
colima ssh -p orch-lab -- sudo sh -c 'cp /etc/docker/daemon.json /etc/docker/daemon.json.orig && python3 - <<E
import json
p="/etc/docker/daemon.json"
d=json.load(open(p)); d["userns-remap"]="default"; d["features"]["containerd-snapshotter"]=False
json.dump(d,open(p,"w"),indent=2)
E
systemctl reset-failed docker; systemctl restart docker'
# With containerd-snapshotter left ON, dockerd refuses to start ("not compatible with userns remapping").
dl info --format '{{.SecurityOptions}} {{.DockerRootDir}}'      # name=userns present, root dir /var/lib/docker/100000.100000
dl build -t orch-lab-claude:test /tmp/orch-lab-work/image       # the image store is empty under the new mapping
```

Root mapping and the hardened run:

```bash
dl run -d --rm --name rootbox --user 0 orch-lab-claude:test sleep 90
dl exec rootbox sh -c 'id -u; cat /proc/self/uid_map'                       # 0, "0 100000 65536"
colima ssh -p orch-lab -- sh -c 'ps -eo uid,comm | grep " sleep"'           # uid 100000 in the VM
dl run --rm --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 768m --cpus 1 \
  --tmpfs /tmp:rw,size=128m,exec -v <LABTMP>/lab:/lab:ro \
  -e LAB_DUMMY_AUTH="<DUMMY_AUTH>" -e LAB_FAKE_OAT="<FAKE_OAT>" -e ANTHROPIC_BASE_URL=http://127.0.0.1:18080 \
  -e ANTHROPIC_AUTH_TOKEN="<DUMMY_AUTH>" orch-lab-claude:test /lab/run-cli.sh b22
```

### B3: the probe script and the results

`/lab/probe.sh` (TCP connect only, no data is ever sent):

```bash
#!/bin/bash
# Result words: REACHABLE (handshake completed), REFUSED (reset), BLOCKED (timeout or unreachable).
p() { name="$1"; host="$2"; port="$3"
  out=$(nc -z -w 3 "$host" "$port" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then r=REACHABLE; elif echo "$out" | grep -qi "refused"; then r=REFUSED; else r=BLOCKED; fi
  printf '%-44s %s\n' "$name" "$r"; }
p "Mac host 192.168.5.2:9222 (Chrome debug)" 192.168.5.2 9222
p "Mac host 192.168.5.2:9224 (Chrome debug twin)" 192.168.5.2 9224
p "Mac host 192.168.5.2:22" 192.168.5.2 22
p "VM itself 192.168.5.3:22 (sshd)" 192.168.5.3 22
p "tailnet 100.124.97.31:8765 (secrets proxy)" 100.124.97.31 8765
p "tailnet 100.64.0.1:443" 100.64.0.1 443
p "RFC1918 10.0.0.1:80" 10.0.0.1 80
p "RFC1918 172.20.0.1:80" 172.20.0.1 80
p "RFC1918 192.168.1.1:80" 192.168.1.1 80
p "link-local metadata 169.254.169.254:80" 169.254.169.254 80
p "VM docker bridge gateway 172.17.0.1:22" 172.17.0.1 22
p "public https registry.npmjs.org:443" registry.npmjs.org 443
p "public dns 1.1.1.1:53" 1.1.1.1 53
p "public tcp 1.1.1.1:443" 1.1.1.1 443
```

```bash
dl run --rm -v <LABTMP>/lab:/lab:ro orch-lab-claude:test /lab/probe.sh      # control (no filter): the first five are REACHABLE
colima ssh -p orch-lab -- sudo sh <LABTMP>/lab/orch-egress.sh                # apply the filter (script below)
dl run --rm -v <LABTMP>/lab:/lab:ro orch-lab-claude:test /lab/probe.sh      # all private/host/tailnet BLOCKED, public REACHABLE
```

### B4: no Docker socket, no Docker API

```bash
dl run --rm orch-lab-claude:test sh -c 'for s in /var/run/docker.sock /run/docker.sock /var/run/containerd/containerd.sock; do [ -e $s ] && echo "$s: PRESENT" || echo "$s: absent"; done
find / -xdev \( -name "docker.sock" -o -name "containerd.sock" \) 2>/dev/null | wc -l
for h in 172.17.0.1 192.168.5.3; do for p in 2375 2376; do nc -z -w 2 $h $p >/dev/null 2>&1 && echo "docker API $h:$p REACHABLE" || echo "docker API $h:$p not reachable"; done; done'
```

## The egress filter: `/usr/local/sbin/orch-egress.sh` (final form, as installed in the VM)

Idempotent. DOCKER-USER for routed traffic, INPUT for traffic to the VM itself, ip6tables for IPv6, plus the bridge-netfilter module so
same-bridge rules see traffic.

```sh
#!/bin/sh
# Egress filter for containers on this VM's Docker bridges. Idempotent: it rebuilds its own chains each run.
set -eu
IFACES="docker0 br-+"
# --- routed traffic (container -> outside): DOCKER-USER, evaluated before Docker's own rules
iptables -N DOCKER-USER 2>/dev/null || true
iptables -N ORCH-EGRESS 2>/dev/null || iptables -F ORCH-EGRESS
iptables -A ORCH-EGRESS -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
for net in 192.168.5.0/24 100.64.0.0/10 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 224.0.0.0/4 240.0.0.0/4; do
  iptables -A ORCH-EGRESS -d "$net" -j DROP
done
iptables -A ORCH-EGRESS -j RETURN
iptables -C DOCKER-USER -j ORCH-EGRESS 2>/dev/null || true
# inter-container traffic on the same bridge never leaves the bridge: drop it explicitly
for i in $IFACES; do iptables -D DOCKER-USER -i "$i" -o "$i" -j DROP 2>/dev/null || true; done
for i in $IFACES; do iptables -D DOCKER-USER -i "$i" -j ORCH-EGRESS 2>/dev/null || true; done
for i in $IFACES; do iptables -I DOCKER-USER 1 -i "$i" -j ORCH-EGRESS; iptables -I DOCKER-USER 1 -i "$i" -o "$i" -j DROP; done
# replies of an allowed same-bridge connection must pass (an allow rule for one destination only matches the request direction)
for i in $IFACES; do iptables -D DOCKER-USER -i "$i" -o "$i" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN 2>/dev/null || true; iptables -I DOCKER-USER 1 -i "$i" -o "$i" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN; done
# the kernel must show bridged traffic to iptables, or same-bridge rules never see it
modprobe br_netfilter; sysctl -qw net.bridge.bridge-nf-call-iptables=1
# --- traffic to the VM itself (sshd, the DNS forwarder, the Docker API if it listened): INPUT
iptables -N ORCH-INPUT 2>/dev/null || iptables -F ORCH-INPUT
iptables -A ORCH-INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -A ORCH-INPUT -p udp -d 192.168.5.3 --dport 53 -j ACCEPT
iptables -A ORCH-INPUT -p tcp -d 192.168.5.3 --dport 53 -j ACCEPT
iptables -A ORCH-INPUT -j DROP
for i in $IFACES; do iptables -D INPUT -i "$i" -j ORCH-INPUT 2>/dev/null || true; iptables -I INPUT 1 -i "$i" -j ORCH-INPUT; done
# --- IPv6: nothing is routed for containers
for i in $IFACES; do ip6tables -D FORWARD -i "$i" -j DROP 2>/dev/null || true; ip6tables -I FORWARD 1 -i "$i" -j DROP; done
```

VM facts the script relies on: the VM is 192.168.5.3 (its own DNS forwarder on :53, sshd on :22), the Mac is 192.168.5.2, the VM has only
link-local IPv6. Re-check them if Colima/Lima networking changes.

The two extra allow rules used by E5 and E6 are NOT in the script; they were added by hand and belong to the design that needs them:

```bash
# E5: the dual-homed forward proxy on the internal task network (request direction only; replies pass via the established rule)
iptables -I DOCKER-USER 1 -i "br-+" -o "br-+" -d 172.30.0.2 -p tcp -m multiport --dports 3128,3129 -j RETURN
# E6: the Claude proxy on the Mac, exactly one host port (inserted as rule 2 of ORCH-EGRESS, after the established accept)
iptables -I ORCH-EGRESS 2 -d 192.168.5.2 -p tcp --dport 18443 -j RETURN
```

## The profile config: `~/.colima/orch-lab/colima.yaml` (what changed from the defaults)

```yaml
# E1: no port forwarding from the VM to the Mac (the docker.sock forward stays)
portForwarder: none

# B2 + E4: merged into /etc/docker/daemon.json at EVERY start (Colima regenerates the file, a manual edit is lost)
docker:
  userns-remap: default
  features:
    containerd-snapshotter: false

mounts:
  - location: <LABTMP>
    writable: true

# E4: the egress script and its systemd unit, installed on every start (scripts must be idempotent)
provision:
  - mode: system
    script: |
      echo <BASE64_OF_orch-egress.sh> | base64 -d > /usr/local/sbin/orch-egress.sh
      chmod 0755 /usr/local/sbin/orch-egress.sh
      echo <BASE64_OF_orch-egress.service> | base64 -d > /etc/systemd/system/orch-egress.service
      echo br_netfilter > /etc/modules-load.d/br_netfilter.conf
      systemctl daemon-reload
      systemctl enable orch-egress.service >/dev/null 2>&1
      systemctl --no-block restart orch-egress.service
```

The profile file was edited with this generator (it produced the YAML above; `BASE64_*` are `base64.b64encode` of the two files in this document):

```python
import base64, os
tmp = open('/tmp/orch-lab-tmp.txt').read().strip()
script = open(tmp + '/lab/orch-egress.sh').read()
script = script.replace('iptables -N ORCH-EGRESS', 'iptables -N DOCKER-USER 2>/dev/null || true\niptables -N ORCH-EGRESS', 1)
b64 = base64.b64encode(script.encode()).decode()
unit = open('/path/to/orch-egress.service').read()          # the unit shown below
ub64 = base64.b64encode(unit.encode()).decode()
prov = f"""provision:
  - mode: system
    script: |
      echo {b64} | base64 -d > /usr/local/sbin/orch-egress.sh
      chmod 0755 /usr/local/sbin/orch-egress.sh
      echo {ub64} | base64 -d > /etc/systemd/system/orch-egress.service
      echo br_netfilter > /etc/modules-load.d/br_netfilter.conf
      systemctl daemon-reload
      systemctl enable orch-egress.service >/dev/null 2>&1
      systemctl --no-block restart orch-egress.service
"""
dock = """docker:
  userns-remap: default
  features:
    containerd-snapshotter: false
"""
p = os.path.expanduser('~/.colima/orch-lab/colima.yaml')
s = open(p).read()
assert 'docker: {}' in s and 'provision: null' in s
s = s.replace('docker: {}', dock.rstrip('\n'), 1).replace('provision: null', prov.rstrip('\n'), 1)
open(p, 'w').write(s)
```

(`portForwarder` was changed with `sed -i '' 's/^portForwarder: ssh/portForwarder: none/' ~/.colima/orch-lab/colima.yaml`.)

Applying a changed profile: `colima stop -p orch-lab; colima start orch-lab; docker context use colima`.

## The systemd unit: `/etc/systemd/system/orch-egress.service`

```ini
[Unit]
Description=Orchestrator worker egress filter (re-applied whenever Docker (re)starts)
After=docker.service
Requires=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/orch-egress.sh
[Install]
WantedBy=docker.service multi-user.target
```

Verified: after a VM restart the rules, `br_netfilter` and `userns-remap` are present; flushing the chains and `systemctl restart docker`
re-applies them. Rapid successive Docker restarts hit systemd's start limit on `docker.service`; `systemctl reset-failed docker orch-egress`
and a pause of about 12 seconds fixes it.

## E1: port forwards

```bash
# default config: listeners in the VM and PUBLISHED container ports appear on the Mac bound to * (reachable via the LAN address too)
colima ssh -p orch-lab -- sh -c 'nohup python3 -m http.server 19001 --bind 0.0.0.0 >/dev/null 2>&1 &'
dl run -d --rm --name e1c -p 19002:8000 orch-lab-claude:test python -m http.server 8000
for p in 19001 19002; do
  echo "port $p: pids=$(lsof -t -nP -iTCP:$p -sTCP:LISTEN | sort -u | wc -l) bound=$(lsof -nP -iTCP:$p -sTCP:LISTEN -Fn | grep '^n' | sort -u) curl=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/)"
done
IP=$(ipconfig getifaddr en0); curl -s -m 3 -o /dev/null -w '%{http_code}\n' http://$IP:19001/      # 200: reachable from the LAN
# (an unpublished container listener, port 8001, did not appear on the Mac)

# the fix: portForwarder: none in the profile config, then restart the VM (restore the docker context)
sed -i '' 's/^portForwarder: ssh/portForwarder: none/' ~/.colima/orch-lab/colima.yaml
colima stop -p orch-lab; colima start orch-lab; docker context use colima
# re-run the listeners: host listeners=0, curl from the host fails, the listener still answers INSIDE the VM
```

## E2: cross-task isolation

```bash
mkdir -p <LABTMP>/tasks/A <LABTMP>/tasks/B; echo A-secret-canary > <LABTMP>/tasks/A/a.txt; echo B-secret-canary > <LABTMP>/tasks/B/b.txt
dl run -d --rm --name taskA -v <LABTMP>/tasks/A:/work orch-lab-claude:test sleep 300
dl run -d --rm --name taskB -v <LABTMP>/tasks/B:/work orch-lab-claude:test python -m http.server 8000
dl exec taskA sh -c 'ls /work; find / -xdev -name b.txt 2>/dev/null | wc -l; ls /work/../tasks 2>&1 | head -1; grep -c orch-lab-mount /proc/self/mountinfo; ps -e | grep -c http.server'
BIP=$(dl inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' taskB)
dl exec taskA sh -c "nc -z -w 3 $BIP 8000 && echo REACHABLE || echo BLOCKED"      # default bridge: REACHABLE
# loading the bridge netfilter module makes the same-bridge DROP in orch-egress.sh effective:
colima ssh -p orch-lab -- sudo sh -c 'modprobe br_netfilter && sysctl -w net.bridge.bridge-nf-call-iptables=1'
dl run --rm orch-lab-claude:test sh -c "nc -z -w 3 $BIP 8000 && echo REACHABLE || echo BLOCKED"   # BLOCKED
# one network per task also isolates tasks (no module needed):
dl network create labA; dl network create labB
dl run -d --rm --name tB --network labB orch-lab-claude:test python -m http.server 8000
dl run --rm --network labA orch-lab-claude:test sh -c "nc -z -w 3 <IP_OF_tB> 8000 && echo REACHABLE || echo BLOCKED"   # BLOCKED
```

## E3: IPv6

```bash
dl run --rm -v <LABTMP>/lab:/lab:ro orch-lab-claude:test sh -c '
echo "container global IPv6 addresses: $(ip -6 -o addr show scope global | wc -l)"
r() { nc -6 -z -w 3 "$2" "$3" >/dev/null 2>&1 && echo "$1 REACHABLE" || echo "$1 BLOCKED"; }
r "public host over IPv6 (cloudflare)" 2606:4700:4700::1111 443
r "public host over IPv6 (google)" 2001:4860:4860::8888 443
r "VM link-local gateway" fe80::1%eth0 22
r "::1 port 9222" ::1 9222'
colima ssh -p orch-lab -- sudo ip6tables -S FORWARD | grep -c 'docker0\|br-'      # the FORWARD drops from orch-egress.sh
```

## E4: persistence

```bash
colima ssh -p orch-lab -- sudo sh -c 'echo "DOCKER-USER rules: $(iptables -S DOCKER-USER | grep -c "^-A")  ORCH chains: $(iptables -S | grep -c "^-N ORCH")  br_netfilter: $(lsmod | grep -c br_netfilter)"; docker info --format "{{.SecurityOptions}}"; grep -c userns-remap /etc/docker/daemon.json'
colima stop -p orch-lab; colima start orch-lab; docker context use colima
# same check again. Without the docker: section and the provision script everything above is gone after the restart
# (iptables rules, br_netfilter, AND userns-remap: Colima regenerates /etc/docker/daemon.json). Only colima.yaml persists.
# With them: all present again. Re-application test:
colima ssh -p orch-lab -- sudo sh -c 'iptables -F ORCH-EGRESS; iptables -F ORCH-INPUT; systemctl restart docker; sleep 6; iptables -S ORCH-EGRESS | grep -c "^-A"'
```

## E5: hostname allowlist (internal network plus dual-homed forward proxy)

`/lab/fproxy.mjs`:

```js
// Lab forward proxy: hostname allowlist for CONNECT (HTTPS) only. Refuses everything else. No header values are logged.
import http from 'node:http';
import net from 'node:net';
const ALLOW = new Set(['registry.npmjs.org:443']);
const log = (o) => console.log(JSON.stringify(o));
const server = http.createServer((req, res) => {
  // a plain (non CONNECT) proxied request, absolute-URI or not, is refused
  log({ kind: 'plain', method: req.method, result: 'REFUSED' });
  res.writeHead(403, { 'content-type': 'text/plain' }); res.end('refused');
});
server.on('connect', (req, clientSocket, head) => {
  const target = String(req.url);
  if (!ALLOW.has(target.toLowerCase())) { log({ kind: 'connect', target, result: 'REFUSED' }); clientSocket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return; }
  const [host, port] = target.split(':');
  const upstream = net.connect(Number(port), host, () => {
    log({ kind: 'connect', target, result: 'ALLOWED' });
    clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    upstream.write(head); upstream.pipe(clientSocket); clientSocket.pipe(upstream);
  });
  upstream.on('error', () => clientSocket.end('HTTP/1.1 502 Bad Gateway\r\n\r\n'));
  clientSocket.on('error', () => upstream.destroy());
});
server.listen(3128, '0.0.0.0', () => log({ listening: 3128 }));
// stand-in for the Claude proxy port: answers 200 to anything
http.createServer((req, res) => { res.writeHead(200); res.end('claude-proxy-stand-in'); }).listen(3129, '0.0.0.0');
```

```bash
dl network create --internal --subnet 172.30.0.0/24 task-net
dl run -d --rm --name lab-proxy --network bridge -v <LABTMP>/lab:/lab:ro orch-lab-claude:test node /lab/fproxy.mjs
dl network connect --ip 172.30.0.2 task-net lab-proxy          # dual-homed: bridge (public egress) plus the internal task network
colima ssh -p orch-lab -- sudo iptables -I DOCKER-USER 1 -i "br-+" -o "br-+" -d 172.30.0.2 -p tcp -m multiport --dports 3128,3129 -j RETURN
dl run --rm --network task-net -e https_proxy=http://172.30.0.2:3128 -e http_proxy=http://172.30.0.2:3128 orch-lab-claude:test sh -c '
r() { name="$1"; shift; if "$@" >/dev/null 2>&1; then echo "$name ALLOWED/REACHABLE"; else echo "$name REFUSED/BLOCKED"; fi; }
r "via proxy: https://registry.npmjs.org (listed)" curl -s -m 12 -o /dev/null --fail https://registry.npmjs.org/
r "via proxy: https://example.com (NOT listed)" curl -s -m 12 -o /dev/null --fail https://example.com/
r "via proxy: https://api.github.com (NOT listed)" curl -s -m 12 -o /dev/null --fail https://api.github.com/
r "via proxy: plain http://example.com (NOT listed)" curl -s -m 12 -o /dev/null --fail http://example.com/
r "Claude proxy stand-in 172.30.0.2:3129" curl -s -m 5 -o /dev/null --fail --noproxy "*" http://172.30.0.2:3129/
r "direct 443 to 1.1.1.1 (no proxy)" nc -z -w 3 1.1.1.1 443
r "direct 443 to registry IP 104.16.0.1" nc -z -w 3 104.16.0.1 443
r "direct 53 to 1.1.1.1 (DNS exfil path)" nc -z -w 3 1.1.1.1 53
r "https without proxy to non-listed host" curl -s -m 8 -o /dev/null --fail --noproxy "*" https://example.com/
r "https without proxy to the listed host" curl -s -m 8 -o /dev/null --fail --noproxy "*" https://registry.npmjs.org/
r "resolve an external name (getent example.com)" getent hosts example.com'
dl logs lab-proxy | grep -v listening | sort | uniq -c        # the proxy's verdicts, names only
```

Result: only the listed host through the proxy and the stand-in port are ALLOWED; everything else BLOCKED, external names do not resolve.

## E6: Claude proxy abuse (synthetic), on the Mac at 127.0.0.1

Environment for both processes (values are random per run; never printed):

```bash
export E6_PORT=18443 E6_UPSTREAM_PORT=18444 E6_RUN_SECRET="run-secret-<hex>" E6_EXPIRED_SECRET="expired-secret-<hex>" E6_FAKE_UPSTREAM_KEY="fake-upstream-key-<hex>"
python3 e6_stub.py > stub.log 2>&1 &
python3 e6_proxy.py > proxy.log 2>&1 &
lsof -nP -iTCP:18443 -iTCP:18444 -sTCP:LISTEN -Fn | grep '^n'     # n127.0.0.1:18443 n127.0.0.1:18444 (loopback only)
colima ssh -p orch-lab -- sudo iptables -I ORCH-EGRESS 2 -d 192.168.5.2 -p tcp --dport 18443 -j RETURN     # the only host port opened
```

### The proxy's allow and refuse rules: `e6_proxy.py`

```python
#!/usr/bin/env python3
"""Synthetic Claude proxy for the isolation lab. Stdlib only. Binds 127.0.0.1. Logs verdict words, never header values.

Allows only: POST /v1/messages (optionally ?beta=true), body <= 1 MiB, a valid unexpired per-run secret
(x-api-key or Authorization: Bearer), at most RATE requests per WINDOW seconds per secret. It then replaces the auth with a FAKE
upstream key and forwards ONLY to the local stub upstream (never Anthropic)."""
import asyncio, hmac, json, os, sys, time

PORT = int(os.environ["E6_PORT"]); UP_PORT = int(os.environ["E6_UPSTREAM_PORT"])
RUN_SECRET = os.environ["E6_RUN_SECRET"]; EXPIRED_SECRET = os.environ["E6_EXPIRED_SECRET"]
FAKE_UPSTREAM_KEY = os.environ["E6_FAKE_UPSTREAM_KEY"]
SECRETS = {RUN_SECRET: time.time() + 3600, EXPIRED_SECRET: time.time() - 5}   # secret -> expiry
RATE, WINDOW, MAX_BODY = 8, 20.0, 1 << 20
hits: dict[str, list[float]] = {}

def verdict(word, method, path, why):
    print(json.dumps({"verdict": word, "method": method, "path": path[:80], "why": why}), flush=True)

async def respond(w, code, text):
    body = text.encode()
    w.write(f"HTTP/1.1 {code} X\r\ncontent-type: text/plain\r\ncontent-length: {len(body)}\r\nconnection: close\r\n\r\n".encode() + body)
    await w.drain(); w.close()

async def handle(r, w):
    try:
        line = await asyncio.wait_for(r.readline(), 10)
        parts = line.decode("latin1").strip().split(" ")
        if len(parts) != 3: return await respond(w, 400, "bad request line")
        method, target, _ = parts
        headers = {}
        while True:
            h = await asyncio.wait_for(r.readline(), 10)
            if h in (b"\r\n", b"\n", b""): break
            k, _, v = h.decode("latin1").partition(":"); headers[k.strip().lower()] = v.strip()
        if method == "CONNECT":
            verdict("REFUSED", method, target, "CONNECT"); return await respond(w, 405, "no CONNECT")
        if not target.startswith("/"):
            verdict("REFUSED", method, target, "absolute-URI form"); return await respond(w, 400, "origin-form only")
        path, _, query = target.partition("?")
        if method != "POST":
            verdict("REFUSED", method, target, "method"); return await respond(w, 405, "POST only")
        if path != "/v1/messages" or query not in ("", "beta=true"):
            verdict("REFUSED", method, target, "path or query not on the allowlist"); return await respond(w, 404, "not allowed")
        presented = headers.get("x-api-key") or (headers.get("authorization", "")[7:] if headers.get("authorization", "").lower().startswith("bearer ") else "")
        match = next((s for s in SECRETS if presented and hmac.compare_digest(presented, s)), None)
        if match is None:
            verdict("REFUSED", method, target, "no or unknown run secret"); return await respond(w, 401, "unauthorized")
        if SECRETS[match] < time.time():
            verdict("REFUSED", method, target, "run secret expired"); return await respond(w, 401, "expired")
        now = time.time(); recent = [t for t in hits.get(match, []) if now - t < WINDOW]
        if len(recent) >= RATE:
            verdict("REFUSED", method, target, "rate limit"); return await respond(w, 429, "slow down")
        hits[match] = recent + [now]
        n = int(headers.get("content-length", "0") or 0)
        if n > MAX_BODY:
            verdict("REFUSED", method, target, "request too large"); return await respond(w, 413, "too large")
        body = await asyncio.wait_for(r.readexactly(n), 20) if n else b""
        ur, uw = await asyncio.open_connection("127.0.0.1", UP_PORT)   # the ONLY upstream: the local stub
        uw.write(f"POST /v1/messages HTTP/1.1\r\nhost: stub\r\nx-api-key: {FAKE_UPSTREAM_KEY}\r\nanthropic-version: 2023-06-01\r\ncontent-type: application/json\r\ncontent-length: {len(body)}\r\nconnection: close\r\n\r\n".encode() + body)
        await uw.drain(); data = await ur.read(65536); uw.close()
        verdict("ALLOWED", method, target, "forwarded to stub upstream"); w.write(data); await w.drain(); w.close()
    except Exception as e:
        try: await respond(w, 400, "bad request")
        except Exception: pass

async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", PORT)
    print(json.dumps({"listening": PORT}), flush=True)
    async with srv: await srv.serve_forever()
asyncio.run(main())
```

The rule table, in the order the proxy decides:

| Order | Condition | Verdict |
|---|---|---|
| 1 | method CONNECT | REFUSED 405 |
| 2 | request target not in origin-form (absolute-URI) | REFUSED 400 |
| 3 | method not POST | REFUSED 405 |
| 4 | path not exactly `/v1/messages`, or query other than none or `beta=true` (no normalisation: `..`, `//`, `%6d` all refused) | REFUSED 404 |
| 5 | run secret missing or unknown (`x-api-key` or `Authorization: Bearer`, constant-time compare) | REFUSED 401 |
| 6 | run secret expired | REFUSED 401 |
| 7 | more than 8 requests per 20 s per secret (counted before the size check) | REFUSED 429 |
| 8 | body larger than 1 MiB | REFUSED 413 |
| 9 | everything else | ALLOWED: auth replaced by the fake upstream key, forwarded only to 127.0.0.1:E6_UPSTREAM_PORT |

### The stub upstream: `e6_stub.py`

```python
#!/usr/bin/env python3
"""Local stub upstream: records WHICH key arrived (words only) and answers 200."""
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
FAKE = os.environ["E6_FAKE_UPSTREAM_KEY"]; RUN = os.environ["E6_RUN_SECRET"]
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        k = self.headers.get("x-api-key", "")
        saw = "FAKE_UPSTREAM" if k == FAKE else "RUN_SECRET_LEAKED" if k == RUN else "NONE" if not k else "OTHER"
        self.rfile.read(int(self.headers.get("content-length", "0") or 0))
        print(json.dumps({"stub_saw_key": saw, "path": self.path}), flush=True)
        b = json.dumps({"id": "msg_stub", "type": "message", "role": "assistant", "model": "stub", "content": [{"type": "text", "text": "stub"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(os.environ["E6_UPSTREAM_PORT"])), H).serve_forever()
```

### The abuse matrix: `/lab/e6-tests.sh` (run in a container on the default bridge with `-e RUN=<RUN_SECRET> -e EXPIRED=<EXPIRED_SECRET>`)

```bash
#!/bin/bash
P="http://192.168.5.2:18443"
body='{"model":"x","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'
t() { name="$1"; shift; code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$@" 2>/dev/null); [ "$code" = "200" ] && v=ALLOWED || v="REFUSED($code)"; printf '%-62s %s\n' "$name" "$v"; }
H='-H content-type:application/json'
t "POST /v1/messages, run secret in x-api-key"            -X POST $H -H "x-api-key: $RUN" -d "$body" $P/v1/messages
t "POST /v1/messages, run secret as Authorization Bearer" -X POST $H -H "Authorization: Bearer $RUN" -d "$body" $P/v1/messages
t "POST /v1/messages?beta=true (the CLI form)"            -X POST $H -H "x-api-key: $RUN" -d "$body" "$P/v1/messages?beta=true"
t "POST /v1/messages, wrong secret"                       -X POST $H -H "x-api-key: not-the-secret" -d "$body" $P/v1/messages
t "POST /v1/messages, no credential"                      -X POST $H -d "$body" $P/v1/messages
t "POST /v1/messages, EXPIRED run secret"                 -X POST $H -H "x-api-key: $EXPIRED" -d "$body" $P/v1/messages
t "GET /v1/messages (other method)"                       -X GET -H "x-api-key: $RUN" $P/v1/messages
t "PUT /v1/messages (other method)"                       -X PUT $H -H "x-api-key: $RUN" -d "$body" $P/v1/messages
t "POST /v1/messages/count_tokens (other path)"           -X POST $H -H "x-api-key: $RUN" -d "$body" $P/v1/messages/count_tokens
t "POST /v1/messages/batches (other path)"                -X POST $H -H "x-api-key: $RUN" -d "$body" $P/v1/messages/batches
t "POST /v1/files (other path)"                           -X POST $H -H "x-api-key: $RUN" -d "$body" $P/v1/files
t "GET /v1/models (other path)"                           -X GET -H "x-api-key: $RUN" $P/v1/models
t "POST /v1/messages?x=1 (other query)"                   -X POST $H -H "x-api-key: $RUN" -d "$body" "$P/v1/messages?x=1"
t "POST /v1/messages/../files (traversal)"                -X POST --path-as-is $H -H "x-api-key: $RUN" -d "$body" "$P/v1/messages/../files"
t "POST //v1/messages (double slash)"                     -X POST --path-as-is $H -H "x-api-key: $RUN" -d "$body" "$P//v1/messages"
t "POST /v1/%6dessages (encoded path)"                    -X POST --path-as-is $H -H "x-api-key: $RUN" -d "$body" "$P/v1/%6dessages"
t "absolute-URI request line (POST http://example.com/v1/messages)" -X POST $H -H "x-api-key: $RUN" -d "$body" --request-target "http://example.com/v1/messages" $P
t "CONNECT example.com:443 through the proxy"             -x $P https://example.com/
head -c 2200000 /dev/zero | tr '\0' 'a' > /tmp/big.bin
t "POST /v1/messages with a 2.1 MiB body (size cap)"      -X POST $H -H "x-api-key: $RUN" --data-binary @/tmp/big.bin $P/v1/messages
for i in 1 2 3 4 5 6 7 8 9 10; do code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST $H -H "x-api-key: $RUN" -d "$body" $P/v1/messages); [ "$code" = 200 ] && ok=$((ok+1)) || bad=$((bad+1)); done
printf '%-62s allowed=%s refused=%s (cap 8 per 20 s per secret)\n' "10 rapid POSTs to /v1/messages (rate limit)" "${ok:-0}" "${bad:-0}"
```

```bash
dl run --rm -v <LABTMP>/lab:/lab:ro -e RUN="<RUN_SECRET>" -e EXPIRED="<EXPIRED_SECRET>" orch-lab-claude:test /lab/e6-tests.sh
dl run --rm -v <LABTMP>/lab:/lab:ro orch-lab-claude:test sh -c 'nc -z -w 3 192.168.5.2 9222 && echo 9222-REACHABLE || echo 9222-BLOCKED'   # still BLOCKED
grep -o '"stub_saw_key": "[A-Z_]*"' stub.log | sort | uniq -c        # only FAKE_UPSTREAM: the run secret never reaches upstream
```

### E6: the Agent SDK honours `ANTHROPIC_BASE_URL` with the run secret as the API key

Wait 20 s (rate-limit window), then in a container:

```bash
# /lab/run-sdk-proxy.sh
#   export HOME=/tmp/home; mkdir -p "$HOME"; timeout 60 python /lab/sdk_query.py > /tmp/sdk-proxy.out 2>&1
dl run --rm -v <LABTMP>/lab:/lab:ro -e ANTHROPIC_BASE_URL=http://192.168.5.2:18443 -e ANTHROPIC_API_KEY="<RUN_SECRET>" orch-lab-claude:test /lab/run-sdk-proxy.sh
# proxy.log: 2 x ALLOWED POST /v1/messages?beta=true; the SDK received 3 messages from the stub
```

Stop the Mac-side processes when done: `pkill -f e6_proxy.py; pkill -f e6_stub.py`.

## C: bundle handback with a malicious Worker clone (all scratch under `<LABTMP>/c`)

Run in bash. Canary scripts only write a marker file, so a fired canary means host code ran.

```bash
LAB=<LABTMP>/c; DL=/tmp/orch-lab-work/dl
rm -rf "$LAB"; mkdir -p "$LAB/canaries" "$LAB/secret-repo"
G() { GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null git -c init.defaultBranch=main -c user.name=lab -c user.email=lab@example.invalid "$@"; }
for c in fsmonitor packhook hook-postcheckout hook-reftx hook-prepush hook-uploadpack sshcmd pager; do
  printf '#!/bin/sh\ndate > "%s/canaries/%s.fired"\nexit 0\n' "$LAB" "$c" > "$LAB/canaries/$c.sh"; chmod +x "$LAB/canaries/$c.sh"; done
echo "host-only secret" > "$LAB/hostsecret.txt"
( cd "$LAB/secret-repo" && G init -q . && echo "SECRET-CANARY" > s.txt && G add s.txt && G commit -qm secret )
SECRET_SHA=$(cd "$LAB/secret-repo" && git rev-parse HEAD)
( G init -q "$LAB/host-repo" && cd "$LAB/host-repo" && echo base > f.txt && G add f.txt && G commit -qm base )
G clone -q "$LAB/host-repo" "$LAB/clone"; cd "$LAB/clone"
G checkout -qb worker/task1; echo "worker change" > w.txt; ln -s "$LAB/hostsecret.txt" leak-link; G add w.txt leak-link; G commit -qm "worker work"
G checkout -q main; echo evil > evil.txt; G add evil.txt; G commit -qm "evil main"; EVIL_MAIN=$(git rev-parse HEAD); G checkout -q worker/task1
echo "$SECRET_SHA" > .git/refs/heads/leakref                 # a ref to a commit that exists only in the alternates repo
git config core.fsmonitor "$LAB/canaries/fsmonitor.sh"
git config uploadpack.packObjectsHook "$LAB/canaries/packhook.sh"
git config core.sshCommand "$LAB/canaries/sshcmd.sh"
git config core.pager "$LAB/canaries/pager.sh"
git config core.hooksPath "$LAB/canaries"
for h in post-checkout reference-transaction pre-push pre-upload-pack; do cp "$LAB/canaries/hook-postcheckout.sh" ".git/hooks/$h"; chmod +x ".git/hooks/$h"; done
echo "$LAB/secret-repo/.git/objects" > .git/objects/info/alternates
ln -s "$LAB/hostsecret.txt" .git/info/symlink-to-host
git config url."$LAB/secret-repo".insteadOf "https://example.invalid/"
```

CONTROL (what a plain fetch from the clone path does): run in `$LAB/host-repo`:

```bash
timeout 60 git fetch -q --no-tags "$LAB/clone" 'worker/task1:refs/remotes/worker/control' 'leakref:refs/remotes/worker/leak'
ls "$LAB/canaries" | grep -c '\.fired$'                                   # 0 on git 2.56.0: nothing executed
git cat-file -e "$SECRET_SHA" && echo "LEAK: the alternates-only object is now in the host repo"   # yes: a real data leak
# control 2: git status INSIDE the hostile clone fires core.fsmonitor (host code execution)
( cd "$LAB/clone" && git status --short >/dev/null 2>&1 ); ls "$LAB/canaries" | grep '\.fired$'      # fsmonitor.fired
```

The Worker side: the bundle is created in a container with no network (the host paths in the clone's config do not exist there):

```bash
$DL run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,size=64m \
  -v "$LAB/clone:/work" orch-lab-git:test sh -c 'cd /work && git -c safe.directory="*" bundle create /work/out.bundle worker/task1 main'
```

The host side, exactly the plan's commands (never git inside the clone, never a fetch from the clone path):

```bash
CAP=$((64*1024*1024)); B="$LAB/clone/out.bundle"
[ -f "$B" ] && [ ! -L "$B" ] && echo "regular file, not a symlink: PASS"
[ "$(stat -f %z "$B")" -le "$CAP" ] && echo "size under cap: PASS"
git --version                                                              # pinned minimum, 2.45 or newer
cd "$LAB/host-repo"
timeout 60 env GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c transfer.fsckObjects=true fetch \
  --no-tags --no-recurse-submodules --no-write-fetch-head "$B" 'worker/task1:refs/remotes/worker/task1'
# afterwards: no canary fired; the alternates-only object is absent (git cat-file -e fails); git for-each-ref differs only in
# refs/remotes/worker/task1; host main is not the bundle's evil main; .git/config and the non-sample hooks are unchanged;
# git -c core.hooksPath=/dev/null fsck --full is clean; the symlink is a tree entry only (nothing is checked out)
```

Abuse cases for the host-side checks:

```bash
ln -sf "$LAB/hostsecret.txt" "$LAB/clone/out2.bundle"; [ -f "$LAB/clone/out2.bundle" ] && [ ! -L "$LAB/clone/out2.bundle" ] || echo "symlink bundle: REFUSED"
head -c 120000000 /dev/urandom > "$LAB/clone/huge.bin"; ( cd "$LAB/clone" && G add huge.bin && G commit -qm huge )
$DL run --rm --network none --read-only --cap-drop ALL --tmpfs /tmp:rw,size=64m -v "$LAB/clone:/work" orch-lab-git:test \
  sh -c 'cd /work && git -c safe.directory="*" bundle create /work/big.bundle worker/task1'
[ "$(stat -f %z "$LAB/clone/big.bundle")" -gt "$CAP" ] && echo "huge object bundle: REFUSED by the size cap"
```

## D: proxy abuse (design only, no commands)

See the report in the thread: an unrestricted token-injecting proxy exposes `POST /v1/messages` (including server-side tools and
`mcp_servers`), `count_tokens`, `/v1/messages/batches`, `GET /v1/models`, the Files and Skills APIs and the OAuth profile and usage
endpoints; the allowlist in the E6 rule table, the size cap, the rate limit, a per-run budget and a per-run secret with an expiry bound
that to "spend some quota on allowed models".

## Cleanup (what was run at the end)

```bash
colima delete orch-lab --force            # then: colima list shows only default; docker context ls has no colima-orch-lab
docker context use colima                  # if a start left the lab context selected
rm -rf <LABTMP> /tmp/orch-lab-work /tmp/orch-lab-tmp.txt
pkill -f e6_proxy.py; pkill -f e6_stub.py   # if any were left
```
