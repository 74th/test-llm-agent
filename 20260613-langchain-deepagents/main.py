import os
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_ollama import ChatOllama
from tavily import TavilyClient

model = ChatOllama(
    base_url=os.environ["OLLAMA_URL"],
    model="gemma4:26b-a4b-it-qat",
)
tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

research_instructions = """あなたは自宅用の音声エージェントです。返答は音声化されるので括弧やマークダウンなどの表現は使わず、文章のみで答えて下さい。3行ほどの短い回答で答えてください。"""

agent = create_agent(
    model=model,
    tools=[internet_search],
    system_prompt=research_instructions,
    middleware=[
        SummarizationMiddleware(
            model=model,
            trigger=[("tokens", 12000), ("messages", 30)],
            keep=("messages", 8),
        ),
    ],
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "日本の野鳥について何か知ってる？ internet_searchで調べて答えてみて。"}]},
    stream_mode="updates",
):
    print(chunk)
