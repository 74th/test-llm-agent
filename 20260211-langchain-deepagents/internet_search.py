import os
import asyncio
from typing import Literal
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

agent = create_deep_agent(
    model="gemini-2.5-flash",
    # model="gemini-3-flash-preview",
    tools=[internet_search],
    system_prompt=instruction,
)

async def main():
    # エージェントをストリーミング実行
    print("=== エージェント実行開始 ===\n")

    async for chunk in agent.astream({"messages": [{"role": "user", "content": "今日の和光市の天気は？"}]}):
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
                                if isinstance(item, dict) and 'text' in item:
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
