import asyncio
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, ToolResultBlock, ToolUseBlock, UserMessage
from poc.adapter import ClaudeAgUiAdapter

async def sdk_stream(**_):
    yield AssistantMessage([ToolUseBlock("tool-1", "mcp__weather__get_today_weather", {"city": "東京"})], "claude")
    yield UserMessage([ToolResultBlock("tool-1", "東京は25℃")])
    for text in ["東京は", "25℃です。"]:
        yield StreamEvent("event", "session-1", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})
    yield ResultMessage("success", 10, 8, False, 2, "session-1")

def test_sdk_messages_map_to_ordered_agui_events():
    async def collect():
        return [item async for item in ClaudeAgUiAdapter(sdk_stream).stream("天気は？", thread_id="thread-1", run_id="run-1")]
    events = asyncio.run(collect())
    types = [item["type"] for item in events]
    assert types == ["RUN_STARTED", "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END", "RUN_FINISHED"]
    assert "".join(item["delta"] for item in events if item["type"] == "TEXT_MESSAGE_CONTENT") == "東京は25℃です。"
    assert events[-1]["result"]["sessionId"] == "session-1"
