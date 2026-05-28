"""Smoke test: verify the SDK runs a one-shot query without firing the user's
filesystem hooks. We disable hooks via `setting_sources=[]` (SDK isolation
mode), not via `CLAUDE_DISABLE_HOOKS` env var, which is a no-op in spawned
CLI subprocesses.

Pass criteria:
- model returns "pong"
- no SessionStart / Stop / UserPromptSubmit hook output appears in messages
- wall clock latency is short (no 36k-token hook injection)
"""

import asyncio
import sys
import time

from claude_agent_sdk import query, ClaudeAgentOptions


# Strings that would appear in tool/message output if Marlin's startup hook
# fired (it injects a Memory Hub block and Project Status Map references).
HOOK_FINGERPRINTS = (
    "Memory Hub",
    "project_status_map",
    "MEMORY.md",
    "SessionStart",
    "<system-reminder>",
)


async def main() -> int:
    options = ClaudeAgentOptions(
        system_prompt="Reply with one word.",
        setting_sources=[],
    )
    start = time.monotonic()
    captured: list[str] = []
    async for msg in query(prompt="Say 'pong'.", options=options):
        text = repr(msg)
        captured.append(text)
        print(text)
    elapsed = time.monotonic() - start

    joined = "\n".join(captured)
    leaked = [fp for fp in HOOK_FINGERPRINTS if fp in joined]
    pong_seen = "pong" in joined.lower()

    print("\n--- smoke summary ---")
    print(f"elapsed: {elapsed:.2f}s")
    print(f"pong seen: {pong_seen}")
    print(f"hook fingerprints leaked: {leaked}")

    if leaked:
        print("FAIL: hook output detected in spawned SDK process", file=sys.stderr)
        return 1
    if not pong_seen:
        print("FAIL: model did not return 'pong'", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
