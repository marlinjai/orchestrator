import asyncio
import os

os.environ["CLAUDE_DISABLE_HOOKS"] = "1"

from claude_agent_sdk import query, ClaudeAgentOptions


async def main():
    options = ClaudeAgentOptions(system_prompt="Reply with one word.")
    async for msg in query(prompt="Say 'pong'.", options=options):
        print(repr(msg))


asyncio.run(main())
