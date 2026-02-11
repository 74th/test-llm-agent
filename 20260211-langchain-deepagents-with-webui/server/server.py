import asyncio
import json
import logging
import os
from typing import Literal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph.state import CompiledStateGraph
from tavily import TavilyClient
from deepagents import create_deep_agent

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("websocket")

async def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return await asyncio.to_thread(
        tavily_client.search,
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

instruction = """あなたは自宅に置かれている音声で応答する日本語のAIホームエージェントです。以下のように振る舞ってください。
- 音声エージェントであるため、ユーザーへの応答はすべて日本語で、マークダウンのように構造化された形式ではなく、自然な会話形式で行ってください。
- 音声応答は3文程度に収めてください。
- 知らないことがあれば、internet_searchツールを使って情報を取得し、回答してください。
"""

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def create_agent()-> CompiledStateGraph:
    agent = create_deep_agent(
        model="gemini-2.5-flash",
        # model="gemini-3-flash-preview",
        tools=[internet_search],
        system_prompt=instruction,
    )

    return agent


def _extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


def _extract_thoughts(message) -> str:
    additional = getattr(message, "additional_kwargs", None)
    if not isinstance(additional, dict):
        return ""
    for key in ("reasoning", "thought", "analysis", "thinking"):
        value = additional.get(key)
        if value:
            return str(value)
    return ""


def _truncate_text(text: str, limit: int = 3000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "... (truncated)", True


@app.get("/")
async def root():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    agent = create_agent()
    history: list[dict] = []
    logger.info("WebSocket connected")

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                logger.info("Received message: %s", raw)
                try:
                    payload = json.loads(raw)
                    user_text = payload.get("content", "")
                except json.JSONDecodeError:
                    user_text = raw

                if not user_text:
                    await websocket.send_json({"type": "error", "message": "空のメッセージです。"})
                    continue

                history.append({"role": "user", "content": user_text})
                await websocket.send_json({"type": "assistant_start"})

                assistant_text = ""
                async for chunk in agent.astream({"messages": history}):
                    for node_name, node_data in chunk.items():
                        if node_data is None or "messages" not in node_data:
                            continue

                        await websocket.send_json({"type": "agent_step", "node": node_name})

                        messages = node_data["messages"]
                        if not isinstance(messages, list):
                            messages = [messages]

                        for message in messages:
                            message_type = message.__class__.__name__
                            if message_type == "ToolMessage":
                                tool_name = getattr(message, "name", None) or "tool"
                                tool_content = _extract_text(message.content)
                                tool_content, truncated = _truncate_text(tool_content)
                                if truncated:
                                    logger.info("Tool result truncated: %s", tool_name)
                                await websocket.send_json(
                                    {
                                        "type": "tool_result",
                                        "name": tool_name,
                                        "content": tool_content,
                                    }
                                )
                                continue

                            tool_calls = getattr(message, "tool_calls", None)
                            if tool_calls:
                                for tool_call in tool_calls:
                                    await websocket.send_json(
                                        {
                                            "type": "tool_call",
                                            "name": tool_call.get("name"),
                                            "args": tool_call.get("args"),
                                        }
                                    )

                            thoughts = _extract_thoughts(message)
                            if thoughts:
                                await websocket.send_json(
                                    {"type": "assistant_thought", "content": thoughts}
                                )

                            if message_type not in {"AIMessage", "AIMessageChunk"}:
                                continue

                            text = _extract_text(message.content)
                            if not text:
                                continue

                            assistant_text += text
                            await websocket.send_json(
                                {"type": "assistant_chunk", "content": text}
                            )

                if assistant_text:
                    history.append({"role": "assistant", "content": assistant_text})

                await websocket.send_json({"type": "assistant_end"})
            except Exception as exc:
                logger.exception("WebSocket loop error: %s", exc)
                await websocket.send_json(
                    {"type": "error", "message": "サーバー側でエラーが発生しました。"}
                )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        return
