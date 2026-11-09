#!/usr/bin/env bash
# Install the `orchestrator` CLI as a uv tool with EXACTLY the dependency
# versions in uv.lock.
#
# Why: `uv tool install --editable .` resolves fresh and ignores uv.lock, so the
# installed tool drifted to a newer claude-agent-sdk than the one the Worker
# confinement was proved against (scripts/prove_confinement.py runs against the
# locked version). The lockfile's versions are exported as constraints.
#
#     scripts/install-tool.sh
#
# Re-run it after pulling a change to uv.lock. `orchestrator start` warns when
# the installed claude-agent-sdk differs from uv.lock.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

constraints="$(mktemp "${TMPDIR:-/tmp}/orchestrator-constraints.XXXXXX")"
trap 'rm -f "$constraints"' EXIT

uv export --frozen --no-hashes --no-dev --no-emit-project -o "$constraints" >/dev/null
uv tool install --force --editable . -c "$constraints"

echo
echo "Installed from uv.lock:"
tool_python="$(uv tool dir)/claude-code-orchestrator/bin/python"
"$tool_python" - <<'PY'
import importlib.metadata as m

for name in ("claude-agent-sdk", "mcp", "pyjwt", "cryptography", "starlette", "anyio"):
    print(f"  {name} {m.version(name)}")
PY
