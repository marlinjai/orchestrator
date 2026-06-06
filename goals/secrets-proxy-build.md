---
task: secrets-proxy-build
spec: README.md
---

# Goal

Build the `secrets-proxy` service from scratch at `~/software-dev/secrets-proxy/`. This is a new Go HTTP service + TypeScript MCP server that allows Claude Code and orchestrator workers to run shell commands that require Infisical secrets, without the raw secret values ever appearing in the response. The proxy runs on a Tailscale-only node, injects secrets via Infisical machine identity, redacts output with deterministic regex, and summarizes what happened via a local Ollama model.

Full design: `~/software-dev/ERP-suite/docs/internal/2026-06-06-local-ai-secrets-proxy.md`
Implementation plan with all resolved decisions: `~/software-dev/ERP-suite/docs/internal/2026-06-06-secrets-proxy-implementation-plan.md`

Read both before starting.

## Read first

- The design doc and implementation plan above (complete, self-contained)
- No existing code to reference -- this is a new project from scratch

## File structure to create

```
~/software-dev/secrets-proxy/
├── cmd/proxy/main.go
├── internal/
│   ├── config/config.go
│   ├── redact/redact.go
│   ├── redact/redact_test.go
│   ├── runner/runner.go
│   └── ollama/client.go
├── mcp/
│   ├── package.json
│   ├── tsconfig.json
│   └── src/index.ts
├── deploy/
│   ├── secrets-proxy.service
│   └── setup.sh
├── go.mod
├── go.sum
└── README.md
```

## Go service -- exact spec

**Module:** `github.com/marlinjai/secrets-proxy`

**Go version:** 1.22 (stdlib only, no external deps except the standard `net/http`, `os/exec`, `regexp`, `encoding/json`)

**Entrypoint `cmd/proxy/main.go`:**
- Reads config via `internal/config`
- Registers a single POST `/execute` handler
- Returns `{"error":"unauthorized"}` with 401 if `X-Proxy-Token` header does not match `PROXY_TOKEN` env var
- Returns `{"error":"method not allowed"}` with 405 for non-POST

**`internal/config/config.go`:**
```go
type Config struct {
    ProxyToken               string // PROXY_TOKEN, required
    InfisicalMIToken         string // INFISICAL_MI_TOKEN, required
    OllamaHost               string // OLLAMA_HOST, default: "127.0.0.1:11434"
    ListenAddr               string // LISTEN_ADDR, default: "0.0.0.0:8765"
    InfisicalDomain          string // INFISICAL_DOMAIN, default: "https://infisical.lumitra.co"
    InfisicalDefaultProject  string // INFISICAL_DEFAULT_PROJECT_ID, optional
}
// Load() reads from env, validates ProxyToken and InfisicalMIToken are non-empty, logs.Fatal if missing
```

**`internal/redact/redact.go`:**

Compile these six patterns at package init (use `regexp.MustCompile`):
1. `[A-Za-z0-9+/]{32,}={0,2}` -- high-entropy base64 (API keys, tokens)
2. `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}` -- UUIDs
3. `postgres(?:ql)?://[^\s'"]+` -- Postgres connection strings
4. `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` -- JWT tokens
5. `sk-[A-Za-z0-9]{20,}` -- sk- prefixed keys
6. `st\.[a-zA-Z0-9]+\.[a-zA-Z0-9]+` -- Infisical service tokens

`func Redact(input string) (output string, count int)` replaces all matches with `[REDACTED]` and returns how many substitutions were made total across all patterns. Apply patterns in order; a token may match multiple patterns -- that is fine, it just becomes `[REDACTED]` from the first match and subsequent patterns won't match the placeholder.

**`internal/redact/redact_test.go`:**

Write a table-driven test `TestRedact` with at least one positive case per pattern:
- Base64: `"token = dGVzdHRva2VuMTIzNDU2Nzg5QUJDREVGR0g="` should redact
- UUID: `"id=550e8400-e29b-41d4-a716-446655440000"` should redact
- Postgres: `"DATABASE_URL=postgresql://user:pass@host/db"` should redact
- JWT: `"auth: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"` should redact
- sk- key: `"OPENAI_KEY=sk-proj-abc123DEF456ghi789JKL012"` should redact
- Clean text: `"Migration complete. 5 rows inserted."` should NOT redact, count=0

**`internal/runner/runner.go`:**

```go
type RunResult struct {
    Stdout   string
    Stderr   string
    ExitCode int
    Err      error
}

// Run executes: infisical run --token=<miToken> --projectId=<projectId>
//   --env=<env> --domain=<domain> -- <command>
// in the given workingDir, captures stdout+stderr separately, returns RunResult.
// If projectId is empty, omit --projectId flag (infisical uses default).
// Timeout: 5 minutes (context with cancel).
// Uses os/exec. Command is split by shell word rules -- use shlex-like splitting
// or exec the command via ["sh", "-c", command] to handle pipes and quoted args.
// Use sh -c approach for simplicity.
```

Concretely: build the infisical args, then append `"sh", "-c", command` as the actual executed program. The full exec becomes:
```
infisical run --token=... --projectId=... --env=... --domain=... -- sh -c "<command>"
```

**`internal/ollama/client.go`:**

```go
type SummarizeRequest struct {
    RedactedOutput string
    OllamaHost     string
}

// Summarize calls POST http://<OllamaHost>/api/generate with:
// {
//   "model": "qwen2.5:14b-instruct-q4_K_M",
//   "prompt": "Summarize this command output in 3-5 lines. Report what succeeded or failed. Do not quote any long strings, tokens, or credentials. If content was redacted, do not mention the redacted content.\n\n<output>\n" + redactedOutput + "\n</output>",
//   "stream": false
// }
// Parses response JSON { "response": "..." } and returns the response string.
// Timeout: 60 seconds.
// If Ollama is unreachable or returns error, return the first 500 chars of
// redactedOutput as-is with a note: "[Ollama unavailable -- showing redacted output excerpt]"
```

**Request/response handler in `cmd/proxy/main.go`:**

```go
type ExecuteRequest struct {
    Command    string `json:"command"`
    WorkingDir string `json:"workingDir"`
    Env        string `json:"env"`       // "dev" | "staging" | "production"
    ProjectID  string `json:"projectId"` // optional
}

type ExecuteResponse struct {
    Success       bool   `json:"success"`
    ExitCode      int    `json:"exitCode"`
    Summary       string `json:"summary"`
    RawLines      int    `json:"rawLines"`
    RedactedCount int    `json:"redactedCount"`
}

// On success: decode request, validate Env is one of dev/staging/production,
// call runner.Run, combine stdout+stderr, call redact.Redact on combined output,
// call ollama.Summarize on redacted output, return ExecuteResponse.
// On runner error (non-zero exit): success=false, exitCode=runner result, still
// summarize (so caller knows what failed).
```

## MCP server -- exact spec

**Location:** `mcp/` within the same repo

**Runtime:** Node.js, TypeScript

**Package:** `@marlinjai/secrets-proxy-mcp` (private)

**Dependencies:**
```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

**`mcp/src/index.ts`:**

Stdio MCP server using `@modelcontextprotocol/sdk`. Register one tool:

```typescript
// Tool name: execute_with_secrets
// Description: "Run a shell command on the secrets proxy server.
//   Infisical secrets are injected server-side; raw credential values never
//   appear in the response. Returns a sanitized summary of what the command did."
// Input schema:
{
  command: { type: "string", description: "Shell command to run" },
  workingDir: { type: "string", description: "Absolute working directory on the proxy server" },
  env: { type: "string", enum: ["dev", "staging", "production"], description: "Infisical environment", default: "dev" },
  projectId: { type: "string", description: "Infisical project ID (optional)" },
}
// required: ["command", "workingDir"]
```

Handler: reads `SECRETS_PROXY_URL` (required) and `PROXY_TOKEN` (required) from `process.env`. Makes a fetch POST to `${SECRETS_PROXY_URL}/execute` with `X-Proxy-Token` header and JSON body from tool input. Returns the response body JSON stringified as the tool result content. If fetch fails or returns non-2xx, return an error result.

**`mcp/tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true
  }
}
```

**`mcp/package.json` scripts:**
```json
{
  "build": "tsc",
  "start": "node dist/index.js"
}
```

## Deploy files

**`deploy/secrets-proxy.service`:**
```ini
[Unit]
Description=Secrets Proxy
After=network.target

[Service]
Type=simple
User=root
EnvironmentFile=/etc/secrets-proxy/env
ExecStart=/usr/local/bin/secrets-proxy
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**`deploy/setup.sh`:**

Idempotent script that Marlin runs on the server after Phase 0+1:
1. Copies the compiled binary to `/usr/local/bin/secrets-proxy` (assumes binary built for linux/arm64)
2. Copies the systemd unit to `/etc/systemd/system/`
3. `systemctl daemon-reload && systemctl enable secrets-proxy && systemctl restart secrets-proxy`
4. Runs a health check: `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8765/execute -H "X-Proxy-Token: $PROXY_TOKEN" -d '{"command":"echo ok","workingDir":"/tmp","env":"dev"}'` -- should return 200

Also include a cross-compile note in the script header:
```bash
# Build for the server: GOOS=linux GOARCH=arm64 go build -o secrets-proxy-linux-arm64 ./cmd/proxy
```

## README.md

Write a clear README with:
1. What this is (2 sentences)
2. Architecture diagram (copy from design doc, simplify)
3. Phase 0: server provisioning steps (from implementation plan)
4. Phase 1: Ollama setup steps
5. Phase 2: building + deploying the proxy (run setup.sh)
6. Phase 3: MCP registration snippet for `~/.claude.json`
7. Env vars table
8. How to test end-to-end (curl example)

## Git setup

Initialize a git repo in the project directory. Single commit when done:
```
feat(secrets-proxy): initial implementation

Go HTTP proxy + TypeScript MCP server for secrets-safe command execution.
Injects Infisical secrets server-side, redacts output with deterministic regex,
summarizes via local Ollama model. Secrets never appear in Claude context.
```

Branch name: `main` (it is a new repo, no existing branches).

## Definition of done

- `go build ./cmd/proxy` succeeds (no errors, no missing imports)
- `go test ./...` passes (redact_test.go covers all 6 patterns)
- `cd mcp && npm install && npm run build` succeeds (tsc compiles, dist/index.js exists)
- `deploy/secrets-proxy.service` is a valid systemd unit (syntax: `systemd-analyze verify deploy/secrets-proxy.service` or manual check)
- `README.md` covers all 4 phases with clear steps
- Single git commit on main

## Constraints

- Stay inside `~/software-dev/secrets-proxy/`. Do not modify files outside it.
- Do not push to any remote.
- stdlib only for Go (no go.sum external entries).
- Do not hardcode any real tokens, keys, or IPs. All sensitive values must come from env vars or the env file.
- Do not run the proxy or MCP server -- just build and test.

## Notes

- Phase 4 (wiring into the orchestrator's worker.py) is a separate task and separate goal file. Do not touch the orchestrator repo.
- The MCP server is NOT registered in ~/.claude.json yet -- Marlin does that manually after Phase 0-1 are done and the server is live. Just build the code and document the registration snippet in README.md.
- Ollama model name to use in the ollama client: `qwen2.5:14b-instruct-q4_K_M`
- Infisical binary is assumed to be installed at `/usr/bin/infisical` on the server. The runner should use the bare command name `infisical` (let PATH resolve it).
