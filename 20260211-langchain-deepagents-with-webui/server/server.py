import asyncio
import os
from typing import Literal
from langgraph.graph.state import CompiledStateGraph
from tavily import TavilyClient
from deepagents import create_deep_agent

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

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
- 音声応答は3分程度に収めてください。
- 知らないことがあれば、internet_searchツールを使って情報を取得し、回答してください。
"""

def create_agent()-> CompiledStateGraph:
    agent = create_deep_agent(
        model="gemini-2.5-flash",
        # model="gemini-3-flash-preview",
        tools=[internet_search],
        system_prompt=instruction,
    )

    return agent
