"""Claude Agent SDK to AG-UI event adapter."""
from __future__ import annotations
import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, ToolResultBlock, ToolUseBlock, UserMessage

Event = dict[str, Any]

def event(event_type: str, thread_id: str, run_id: str, **data: Any) -> Event:
    return {"type": event_type, "threadId": thread_id, "runId": run_id, **data}

def sse(item: Event) -> bytes:
    return f"data: {json.dumps(item, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()

class ClaudeAgUiAdapter:
    """Maps SDK messages into protocol events without knowing HTTP or persistence."""
    def __init__(self, source: Callable[..., AsyncIterator[Any]]) -> None:
        self.source = source

    async def stream(self, prompt: str, *, thread_id: str, run_id: str, session_id: str | None = None) -> AsyncIterator[Event]:
        message_id = f"assistant-{run_id}"
        reasoning_id = f"reasoning-{run_id}"
        text_started = False
        reasoning_started = False
        partial_text = ""
        yield event("RUN_STARTED", thread_id, run_id)
        try:
            async for message in self.source(prompt=prompt, session_id=session_id):
                if isinstance(message, StreamEvent):
                    raw = message.event
                    delta = raw.get("delta", {})
                    if raw.get("type") == "content_block_delta" and delta.get("type") == "thinking_delta":
                        if not reasoning_started:
                            reasoning_started = True
                            yield event("REASONING_START", thread_id, run_id, messageId=reasoning_id)
                            yield event("REASONING_MESSAGE_START", thread_id, run_id, messageId=reasoning_id, role="reasoning")
                        content = delta.get("thinking", "")
                        if content:
                            yield event("REASONING_MESSAGE_CONTENT", thread_id, run_id, messageId=reasoning_id, delta=content)
                    elif raw.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        if reasoning_started:
                            yield event("REASONING_MESSAGE_END", thread_id, run_id, messageId=reasoning_id)
                            yield event("REASONING_END", thread_id, run_id, messageId=reasoning_id)
                            reasoning_started = False
                        if not text_started:
                            text_started = True
                            yield event("TEXT_MESSAGE_START", thread_id, run_id, messageId=message_id, role="assistant")
                        content = delta.get("text", "")
                        partial_text += content
                        if content:
                            yield event("TEXT_MESSAGE_CONTENT", thread_id, run_id, messageId=message_id, delta=content)
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            if reasoning_started:
                                yield event("REASONING_MESSAGE_END", thread_id, run_id, messageId=reasoning_id)
                                yield event("REASONING_END", thread_id, run_id, messageId=reasoning_id)
                                reasoning_started = False
                            yield event("TOOL_CALL_START", thread_id, run_id, toolCallId=block.id, toolCallName=block.name, parentMessageId=message_id)
                            yield event("TOOL_CALL_ARGS", thread_id, run_id, toolCallId=block.id, delta=json.dumps(block.input, ensure_ascii=False))
                            yield event("TOOL_CALL_END", thread_id, run_id, toolCallId=block.id)
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            content = block.content if isinstance(block.content, str) else json.dumps(block.content, ensure_ascii=False)
                            yield event("TOOL_CALL_RESULT", thread_id, run_id, toolCallId=block.tool_use_id, messageId=f"tool-{block.tool_use_id}", role="tool", content=content)
                elif isinstance(message, ResultMessage):
                    session_id = message.session_id
            if reasoning_started:
                yield event("REASONING_MESSAGE_END", thread_id, run_id, messageId=reasoning_id)
                yield event("REASONING_END", thread_id, run_id, messageId=reasoning_id)
            if text_started:
                yield event("TEXT_MESSAGE_END", thread_id, run_id, messageId=message_id)
            yield event("RUN_FINISHED", thread_id, run_id, result={"text": partial_text, "messageId": message_id, "sessionId": session_id})
        except Exception as exc:
            yield event("RUN_ERROR", thread_id, run_id, message=str(exc), code=type(exc).__name__)
