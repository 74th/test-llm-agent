"""Minimal Claude Agent SDK agent with an in-process weather tool."""

from collections.abc import MutableSequence
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool
from dotenv import load_dotenv

load_dotenv()

WEATHER_TOOL_NAME = "mcp__weather__get_today_weather"


def build_weather_tool(calls: MutableSequence[dict[str, Any]] | None = None):
    """Build a deterministic tool; ``calls`` is useful for observing executions."""

    @tool(
        "get_today_weather",
        "Return today's dummy weather for the requested city.",
        {"city": str},
    )
    async def get_today_weather(args: dict[str, Any]) -> dict[str, Any]:
        if calls is not None:
            calls.append(dict(args))
        return {
            "content": [{
                "type": "text",
                "text": f"{args['city']}の今日の気温は25℃です（ダミーデータ）。",
            }]
        }

    return get_today_weather


def build_options(weather_tool: Any, model: str | None = None) -> ClaudeAgentOptions:
    """Configure an agent that can call only the sample MCP tool."""
    server = create_sdk_mcp_server(
        name="weather", version="1.0.0", tools=[weather_tool]
    )
    return ClaudeAgentOptions(
        model=model,
        max_turns=3,
        mcp_servers={"weather": server},
        allowed_tools=[WEATHER_TOOL_NAME],
        disallowed_tools=[
            "Bash", "Edit", "Glob", "Grep", "Read", "WebFetch", "WebSearch", "Write"
        ],
        system_prompt=(
            "You are a weather assistant. Always call get_today_weather to answer "
            "weather questions, and report the tool result without changing it."
        ),
    )


async def ask_weather(
    city: str, *, calls: MutableSequence[dict[str, Any]], model: str | None = None
):
    """Ask Claude for weather and return all SDK messages."""
    options = build_options(build_weather_tool(calls), model=model)
    messages = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            f"{city}の今日の気温を、必ず get_today_weather ツールを使って教えてください。"
        )
        async for message in client.receive_response():
            messages.append(message)
    return messages
