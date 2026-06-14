import os
import uuid
from typing import Literal, cast

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from tavily import TavilyClient

from llama_reasoning_chat import LlamaServerReasoningChatModel

select_chat_model = "llama"

if select_chat_model == "ollama":
    model = ChatOllama(
        base_url=os.environ["OLLAMA_URL"],
        model="gemma4:26b-a4b-it-qat",
    )

elif select_chat_model == "openai":
    model = ChatOpenAI(
        base_url="http://constance:30323/v1",
        api_key="dummy",
        model="local-model",
        extra_body={"reasoning_format": "none"}
    )

elif select_chat_model == "llama":
    model = LlamaServerReasoningChatModel(
        base_url="http://constance:30323/v1",
        api_key="dummy",
        model="local-model",
        max_tokens=1024*16,
        extra_body={},
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

# 2つのエージェントのための指示（プロンプト）
QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""
RESPONDER_INSTRUCTIONS = """あなたは知識豊富な回答者です。質問に対して丁寧に答え、その後に相手がさらに興味を持てるような関連する質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""

def create_agent_instance(instructions):
    return create_agent(
        model=model,
        tools=[internet_search],
        system_prompt=instructions,
        checkpointer=InMemorySaver(),
        middleware=[
            SummarizationMiddleware(
                model=model,
                trigger=[("tokens", 12000), ("messages", 30)],
                keep=("messages", 8),
            ),
        ],
    )

# エージェントの作成
questioner_agent = create_agent_instance(QUESTIONER_INSTRUCTIONS)
responder_agent = create_agent_instance(RESPONDER_INSTRUCTIONS)

def run_conversation(turns=10):
    # 会話を開始するための初期メッセージ
    message = {"role": "user", "content": "日本の野鳥について話しましょう。"}

    questionaier_thread_id = uuid.uuid4().hex
    responder_thread_id = uuid.uuid4().hex

    for i in range(turns):
        print(f"\n=== Turn {i+1} ===")

        # --- 質問者のターン ---
        print("\n[Questioner]")
        print("Received question:", message["content"])
        result = questioner_agent.invoke(
            {"messages": [message]},
            stream_mode="updates",
            config={"configurable": {"thread_id": questionaier_thread_id}},
        )

        print(result)
        last_q_content = ""
        for chunk in result:
            if isinstance(chunk, dict) and "model" in chunk:
                last_q_content = cast(str, chunk["model"]["messages"][-1].content)

        if last_q_content:
            message = {"role": "user", "content": last_q_content}
        else:
            message = {"role": "user", "content": ""}

        # --- 回答者のターン ---
        print("\n[Responder]")
        print("Received question:", message["content"])
        if i == 0:
            messages = [{"role": "assistant", "content": "日本の野鳥について話しましょう。"},message]
        else:
            messages = [message]
        result = responder_agent.invoke(
            {"messages": messages},
            stream_mode="updates",
            config={"configurable": {"thread_id": responder_thread_id}},
        )

        last_r_content = ""
        for chunk in result:
            if isinstance(chunk, dict) and "model" in chunk:
                last_r_content = cast(str, chunk["model"]["messages"][-1].content)
        print(result)

        if last_r_content:
            # 次の質問者のターンに向けて、回答者の発言を 'user' ロールとして追加
            message = {"role": "user", "content": last_r_content}
        else:
            message = {"role": "user", "content": ""}

if __name__ == "__main__":
    run_conversation(10)
