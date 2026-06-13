import os
from typing import Literal

from deepagents import create_deep_agent
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

research_instructions = """
"""

agent = create_deep_agent(
    model=model,
    tools=[internet_search],
    system_prompt=research_instructions,
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "日本の野鳥について何か知ってる？"}]},
    stream_mode="updates",
    subgraphs=True,
    version="v2",
):
    if chunk["type"] == "updates":
        if chunk["ns"]:
            # Subagent event - namespace identifies the source
            print(f"[subagent: {chunk['ns']}]")
        else:
            # Main agent event
            print("[main agent]")
        print(chunk["data"])
