---
task: secrets-proxy-orchestrator-wire
spec: docs/plans/secrets-proxy-orchestrator-wire.md
---

# Goal

Wire the secrets-proxy `execute_with_secrets` tool into the orchestrator's Worker so that credential-requiring shell commands route through the proxy rather than running directly in Worker context. The Worker currently runs `infisical run` commands via Bash, which injects secrets into the subprocess and can expose them in the transcript sent to Anthropic. After this change, Workers use `execute_with_secrets` for any command needing Infisical secrets.

Context:
- secrets-proxy repo: `~/software-dev/secrets-proxy/`
- Design doc: `~/software-dev/ERP-suite/docs/internal/2026-06-06-local-ai-secrets-proxy.md`
- Proxy running on: `100.124.97.31:8765` (Tailscale-only)
- MCP server binary: `~/software-dev/secrets-proxy/mcp/dist/index.js`
- Tool already registered in Claude Code user config (confirmed working)

Read the orchestrator CLAUDE.md before starting: `~/software-dev/orchestrator/CLAUDE.md`

## Files to change

All changes in `~/software-dev/orchestrator/`:

**`orchestrator/worker.py`** -- `build_worker_options()`:
1. Add the secrets-proxy MCP server to `mcp_servers`:
   ```python
   "secrets-proxy": {
       "type": "stdio",
       "command": "node",
       "args": ["/Users/marlinjai/software-dev/secrets-proxy/mcp/dist/index.js"],
       "env": {
           "SECRETS_PROXY_URL": "http://100.124.97.31:8765",
           "PROXY_TOKEN": os.environ.get("SECRETS_PROXY_TOKEN", ""),
       }
   }
   ```
2. Add `"mcp__secrets-proxy__execute_with_secrets"` to `allowed_tools`

**`WORKER_SYSTEM_PROMPT`** in `orchestrator/worker.py` -- add a section after the hard rules:
```
Tool: execute_with_secrets
Use this instead of Bash for any command that requires Infisical secrets (database
migrations, API calls needing tokens, infisical run wrappers). Pass projectId and path
so the proxy fetches from the right Infisical location. Never run `infisical run`
directly via Bash -- it injects raw secrets into this process.
```

**`orchestrator/guardrails.py`** -- add to the bash denylist (belt-and-suspenders):
- `"infisical run"` -- block direct infisical run from Worker Bash

**`personas/default.md`** -- add a note that Workers have access to `execute_with_secrets` for secret-requiring commands and should prefer it over direct infisical Bash invocations.

## SECRETS_PROXY_TOKEN availability

The Worker's `build_worker_options()` calls `_scrub_anthropic_api_key()` which pops `ANTHROPIC_API_KEY`. `SECRETS_PROXY_TOKEN` is injected by `cc.sh` (via Infisical dotfiles project, dev env). It MUST NOT be scrubbed -- only `ANTHROPIC_API_KEY` is scrubbed. Verify `_scrub_anthropic_api_key()` is not touching other keys. The token passes through to the MCP server subprocess env automatically.

## Definition of done

- `pytest -v` passes (all existing tests green, no regressions)
- `orchestrator/worker.py` has `execute_with_secrets` in `allowed_tools` and `secrets-proxy` in `mcp_servers`
- `WORKER_SYSTEM_PROMPT` mentions the tool and when to use it
- `guardrails.py` blocks direct `infisical run` from Worker Bash
- Single conventional-commit on a branch `feat/secrets-proxy-worker-wiring`
- No secrets hardcoded -- token comes from env

## Constraints

- Do NOT modify the proxy itself (`~/software-dev/secrets-proxy/`) -- only the orchestrator
- Do NOT push to remote
- Do NOT change the Worker's `setting_sources=[]` isolation -- keep it intact
- Worker's `_scrub_anthropic_api_key` must remain scoped to ANTHROPIC_API_KEY only

## Notes

- The `mcp_servers` dict in `build_worker_options()` currently has only `orchestrator-state`. Add `secrets-proxy` alongside it.
- `SECRETS_PROXY_TOKEN` in the Worker MCP server env: if it's empty string (env var not set), the MCP server will exit(1) at startup. That's acceptable -- Workers that need secrets run in sessions launched via cc.sh which injects the token. Bare `orchestrator start` without cc.sh will degrade gracefully (tool registered but MCP server fails to start).
- Phase 4 is a separate concern from Phase 2+3 -- don't touch the proxy code.
