import asyncio
import pathlib
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent
from langchain_aws import ChatBedrock
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from deepagents.backends.filesystem import FilesystemBackend

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

ROOT_DIR = pathlib.Path(__file__).parent
SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

checkpointer = MemorySaver()


@tool("weather_search", description="天気を調べるツール。使い方はSKILLのhow-to-search-weatherを参照。")
# @tool("weather_search", description="天気を調べるツール。都道府県市区町村をつなげた文字を引数にとる。例: 埼玉県さいたま市")
async def whther_search(
    query: str,
):
    """Run a web search"""
    print(f"weather_searchツールが呼び出されました: {query}")
    return "晴れ"


instruction = """あなたは自宅に置かれている音声で応答する日本語のAIホームエージェントです。以下のように振る舞ってください。
- 音声エージェントであるため、ユーザーへの応答はすべて日本語で、マークダウンのように構造化された形式ではなく、自然な会話形式で行ってください。
- 音声応答は3文程度に収めてください。
"""
agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=ROOT_DIR.as_posix()),
    model=ChatBedrock(
        # model="jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        model="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        region="ap-northeast-1",
    ),
    # model="gemini-3-flash-preview",
    tools=[whther_search],
    skills=[SKILLS_DIR.as_posix()],
    system_prompt=instruction,
    checkpointer=checkpointer,
)

question = "今日の和光市の天気は？"
# question = "ペンテルパンテルとは何ですか？"

async def main():
    # エージェントをストリーミング実行
    print("=== エージェント実行開始 ===\n")

    async for chunk in agent.astream(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": "123456"}},
    ):
        # チャンクの各ノードを処理
        for node_name, node_data in chunk.items():
            # node_dataがNoneの場合はスキップ
            if node_data is None:
                continue

            if "messages" in node_data:
                messages = node_data["messages"]
                # messagesがリストでない場合（Overwriteなど）は、リストに変換
                if not isinstance(messages, list):
                    messages = [messages]

                for message in messages:
                    # ツールの実行結果
                    if message.__class__.__name__ == "ToolMessage":
                        print(f"✅ ツール実行完了\n")
                        continue

                    # AIの応答（思考や会話）
                    if hasattr(message, "content") and message.content:
                        content = message.content
                        # contentがリストの場合、textを抽出
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and "text" in item:
                                    print(f"💭 {item['text']}")
                        else:
                            print(f"💭 {content}")

                    # ツール呼び出し
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            print(f"🔧 ツール実行: {tool_call['name']}")
                            print(f"   引数: {tool_call['args']}")

    print("\n=== 実行完了 ===")


if __name__ == "__main__":
    asyncio.run(main())
