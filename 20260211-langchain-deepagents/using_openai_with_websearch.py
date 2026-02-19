from datetime import datetime, timezone, timedelta

import pathlib
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.tracers.langchain import wait_for_all_tracers
from langchain_openai import ChatOpenAI

WORKSPACE_DIR = pathlib.Path(__file__).parent / "workspace"
SKILLS_DIR = WORKSPACE_DIR / "skills"

checkpointer = MemorySaver()

JST = timezone(timedelta(hours=+9), 'JST')
current_date = datetime.now(JST).strftime("%Y-%m-%d")

instruction = f"""あなたは自宅に置かれている音声で応答する日本語のAIホームエージェントです。以下のように振る舞ってください。
- 音声エージェントであるため、ユーザーへの応答はすべて日本語で、マークダウンのように構造化された形式ではなく、自然な会話形式で行ってください。
- 音声応答は3文程度に収めてください。
- 今日は {current_date} です。ユーザーからの質問に答える際は、現在の日付を考慮してください。

OpenAIに備わったweb_search_previewツールを活用してください
"""

# 要: OPENAI_API_KEY 環境変数
model = ChatOpenAI(
    model="gpt-5.2",
    use_responses_api=True,
    output_version="responses/v1",
)

agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=WORKSPACE_DIR.as_posix()),
    model=model,
    # Web検索ツールを有効化
    tools=[{"type": "web_search_preview"}],
    system_prompt=instruction,
    checkpointer=checkpointer,
)


async def query(question: str):
    # エージェントをストリーミング実行
    print("=== エージェント実行開始 ===\n")

    async for chunk in agent.astream(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": "123456"}},
    ):
        # チャンクの各ノードを処理
        for n, (node_name, node_data) in enumerate(chunk.items()):
            # node_dataがNoneの場合はスキップ
            if node_data is None:
                continue

            print(f"--- ノード {n+1}: {node_name} ---")
            print(f"ノードデータ: {node_data}")

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

    wait_for_all_tracers()
