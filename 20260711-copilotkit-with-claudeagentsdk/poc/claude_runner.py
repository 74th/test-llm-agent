"""Claude Agent SDK execution boundary."""
from __future__ import annotations
import os
from collections.abc import AsyncIterator
from typing import Any
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from weather_agent import build_weather_tool

async def sdk_messages(*, prompt: str, session_id: str | None = None) -> AsyncIterator[Any]:
    options = ClaudeAgentOptions(
        model=os.getenv("ANTHROPIC_MODEL"), resume=session_id,
        include_partial_messages=True, max_turns=5,
        thinking={"type": "enabled", "budget_tokens": int(os.getenv("CLAUDE_THINKING_BUDGET", "2048"))},
        mcp_servers=build_server(), allowed_tools=["mcp__weather__get_today_weather"],
        disallowed_tools=["Bash", "Edit", "Glob", "Grep", "Read", "WebFetch", "WebSearch", "Write"],
        system_prompt="あなたは簡潔な日本語で答えるアシスタントです。天気の質問には必ず get_today_weather を使い、結果をそのまま報告してください。",
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            yield message

def build_server():
    from claude_agent_sdk import create_sdk_mcp_server
    return {"weather": create_sdk_mcp_server(name="weather", version="1.0.0", tools=[build_weather_tool()])}
