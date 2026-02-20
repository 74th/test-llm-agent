import asyncio
import pathlib
import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from tavily import TavilyClient
from pydantic import BaseModel, Field
from deepagents import create_deep_agent
from langchain_aws import ChatBedrock
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.tracers.langchain import wait_for_all_tracers

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

WORKSPACE_DIR = pathlib.Path(__file__).parent / "workspace"
SKILLS_DIR = WORKSPACE_DIR / "skills"

checkpointer = MemorySaver()

class WeatherSearchInput(BaseModel):
    location_name: str = Field(description="都道府県市区町村をつなげた文字列。例: 埼玉県さいたま市")


@tool("weather_search", description="天気を調べるツール", args_schema=WeatherSearchInput)
async def whther_search(
    location_name: str
):
    logger.info(f"weather_searchツールが呼び出されました: {location_name}")
    return "晴れ"


instruction = """あなたは自宅に置かれている音声で応答する日本語のAIホームエージェントです。以下のように振る舞ってください。
- 音声エージェントであるため、ユーザーへの応答はすべて日本語で、マークダウンのように構造化された形式ではなく、自然な会話形式で行ってください。
- 音声応答は3文程度に収めてください。
- **スキルは関連性がありそうであれば必ず参照すること**
- スキルを呼び出すときには、スキルを呼び出すことを明示的に宣言する必要はありません。
"""
agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=WORKSPACE_DIR.as_posix()),

    # Bedrockの Claude
    # model=ChatBedrock(
    #     # model="jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
    #     model="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
    #     region="ap-northeast-1",
    # ),

    # Gemini
    model=ChatGoogleGenerativeAI(model="gemini-3-flash-preview"),
    tools=[whther_search],
    skills=[SKILLS_DIR.as_posix()],
    system_prompt=instruction,
    checkpointer=checkpointer,
)

async def query(question: str):
    # エージェントをストリーミング実行
    logger.info("=== エージェント実行開始 ===\n")

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
                        logger.info("✅ ツール実行完了\n")
                        continue

                    # AIの応答（思考や会話）
                    if hasattr(message, "content") and message.content:
                        content = message.content
                        # contentがリストの場合、textを抽出
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and "text" in item:
                                    logger.info(f"💭 {item['text']}")
                        else:
                            logger.info(f"💭 {content}")

                    # ツール呼び出し
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            logger.info(f"🔧 ツール実行: {tool_call['name']}")
                            logger.info(f"   引数: {tool_call['args']}")

    logger.info("\n=== 実行完了 ===")

    wait_for_all_tracers()
