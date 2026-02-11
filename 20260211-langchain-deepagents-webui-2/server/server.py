import asyncio
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json

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

def create_agent():
    return create_deep_agent(
        model="gemini-2.5-flash",
        # model="gemini-3-flash-preview",
        tools=[internet_search],
        system_prompt=instruction,
    )

app = FastAPI()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "DeepAgent WebSocket Server"}

def format_event(event):
    """イベントを整形してクライアントに送信する形式に変換"""
    formatted_events = []

    for node_name, node_data in event.items():
        if node_name == "model":
            # モデルからの応答を処理
            messages = node_data.get("messages", [])
            for msg in messages:
                # AIメッセージのテキストコンテンツを抽出
                if hasattr(msg, "content"):
                    if isinstance(msg.content, list):
                        for content_item in msg.content:
                            if isinstance(content_item, dict) and content_item.get("type") == "text":
                                text = content_item.get("text", "")
                                if text:
                                    formatted_events.append({
                                        "type": "text",
                                        "content": text
                                    })
                    elif isinstance(msg.content, str):
                        if msg.content:
                            formatted_events.append({
                                "type": "text",
                                "content": msg.content
                            })

                # ツール呼び出しを抽出
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        formatted_events.append({
                            "type": "tool_call",
                            "tool_name": tool_call.get("name", "unknown"),
                            "args": tool_call.get("args", {})
                        })

        elif node_name == "tools":
            # ツール実行結果を処理
            messages = node_data.get("messages", [])
            for msg in messages:
                if hasattr(msg, "content"):
                    try:
                        # ツール実行結果をJSONとして解析
                        result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        formatted_events.append({
                            "type": "tool_result",
                            "tool_name": getattr(msg, "name", "unknown"),
                            "result": result
                        })
                    except:
                        formatted_events.append({
                            "type": "tool_result",
                            "tool_name": getattr(msg, "name", "unknown"),
                            "result": str(msg.content)
                        })

    return formatted_events

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    agent = create_agent()
    # 会話履歴を保持
    conversation_history = []
    # メッセージキュー
    message_queue = asyncio.Queue()
    # 現在実行中のエージェントタスク
    current_agent_task = None

    async def run_agent(user_message):
        """エージェントを実行"""
        # ユーザーメッセージを履歴に追加
        conversation_history.append({"role": "user", "content": user_message})

        # エージェントからの応答を収集
        assistant_messages = []

        try:
            # エージェントを実行（全履歴を渡す）
            async for event in agent.astream({"messages": conversation_history}):
                # イベントを整形
                formatted_events = format_event(event)

                # 整形されたイベントをクライアントに送信
                for formatted_event in formatted_events:
                    await websocket.send_text(json.dumps({
                        "type": formatted_event["type"],
                        "data": formatted_event
                    }))

                    # テキスト応答を履歴用に収集
                    if formatted_event["type"] == "text":
                        assistant_messages.append(formatted_event["content"])

            # アシスタントの応答を履歴に追加
            if assistant_messages:
                full_response = "\n".join(assistant_messages)
                conversation_history.append({"role": "assistant", "content": full_response})

            # 完了メッセージを送信
            await websocket.send_text(json.dumps({
                "type": "complete"
            }))

        except asyncio.CancelledError:
            # タスクがキャンセルされた場合
            await websocket.send_text(json.dumps({
                "type": "interrupted",
                "message": "処理が中断されました"
            }))
            # 未完了の応答も履歴に追加（もしあれば）
            if assistant_messages:
                full_response = "\n".join(assistant_messages)
                conversation_history.append({"role": "assistant", "content": full_response})
            raise

    async def process_agent():
        """エージェント処理ループ"""
        nonlocal current_agent_task

        while True:
            # キューからメッセージを取得
            user_message = await message_queue.get()

            # エージェント実行タスクを作成して実行
            current_agent_task = asyncio.create_task(run_agent(user_message))
            try:
                await current_agent_task
            except asyncio.CancelledError:
                pass

            message_queue.task_done()

    async def receive_messages():
        """メッセージを受信するタスク"""
        nonlocal current_agent_task

        try:
            while True:
                # クライアントからのメッセージを受信
                data = await websocket.receive_text()
                message_data = json.loads(data)
                user_message = message_data.get("message", "")

                # 現在実行中のエージェントタスクがあればキャンセル
                if current_agent_task and not current_agent_task.done():
                    current_agent_task.cancel()
                    try:
                        await current_agent_task
                    except asyncio.CancelledError:
                        pass

                # メッセージをキューに追加
                await message_queue.put(user_message)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
            raise

    try:
        # エージェント処理タスクを起動
        agent_process_task = asyncio.create_task(process_agent())

        # メッセージ受信タスクを実行
        await receive_messages()

    except WebSocketDisconnect:
        print("WebSocket disconnected")
        if agent_process_task and not agent_process_task.done():
            agent_process_task.cancel()
        if current_agent_task and not current_agent_task.done():
            current_agent_task.cancel()
    except Exception as e:
        print(f"Error: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))
        if agent_process_task and not agent_process_task.done():
            agent_process_task.cancel()
        if current_agent_task and not current_agent_task.done():
            current_agent_task.cancel()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
