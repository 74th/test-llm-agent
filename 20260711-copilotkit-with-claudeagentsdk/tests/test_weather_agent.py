import asyncio
import os

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

from weather_agent import WEATHER_TOOL_NAME, ask_weather, build_weather_tool


def test_dummy_weather_tool_returns_fixed_temperature() -> None:
    calls = []
    weather_tool = build_weather_tool(calls)

    result = asyncio.run(weather_tool.handler({"city": "東京"}))

    assert calls == [{"city": "東京"}]
    assert result["content"][0]["text"] == "東京の今日の気温は25℃です（ダミーデータ）。"


@pytest.mark.vertex
def test_claude_agent_calls_weather_tool_via_vertex() -> None:
    if os.getenv("RUN_VERTEX_INTEGRATION") != "1":
        pytest.skip("set RUN_VERTEX_INTEGRATION=1 to run the paid Vertex AI test")

    required = ["ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail(f"missing Vertex AI environment variables: {', '.join(missing)}")
    if os.getenv("CLAUDE_CODE_USE_VERTEX") != "1":
        pytest.fail("CLAUDE_CODE_USE_VERTEX must be set to 1")

    calls = []
    messages = asyncio.run(
        ask_weather("東京", calls=calls, model=os.getenv("ANTHROPIC_MODEL"))
    )

    tool_uses = [
        block
        for message in messages
        if isinstance(message, AssistantMessage)
        for block in message.content
        if isinstance(block, ToolUseBlock)
    ]
    response_text = "".join(
        block.text
        for message in messages
        if isinstance(message, AssistantMessage)
        for block in message.content
        if isinstance(block, TextBlock)
    )

    assert len(calls) == 1, "the in-process tool was not executed exactly once"
    assert calls[0]["city"].casefold() in {"東京", "tokyo"}
    assert any(block.name == WEATHER_TOOL_NAME for block in tool_uses)
    assert "25" in response_text
