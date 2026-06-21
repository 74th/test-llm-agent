import os
import uuid

import streamlit as st
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from llama_reasoning_chat import LlamaServerReasoningChatModel

model = LlamaServerReasoningChatModel(
    base_url="http://localhost:11434/v1",
    api_key="dummy",
    model="gemma4:26b",
    extra_body={},
)


# 2つのエージェントのための指示（プロンプト）
QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""


def create_agent_instance(instructions):
    return create_agent(
        model=model,
        tools=[],
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


def check_weather(location: str) -> str:
    """Return the weather forecast for the specified location."""
    return f"It's always sunny in {location}"


def main():
    agent = create_agent_instance(QUESTIONER_INSTRUCTIONS)
    # 3. Streamlit UIの実装
    st.title("AI エージェント")

    if "thread_id" not in st.session_state.messages:
        st.session_state.thread_id = uuid.uuid4().hex

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 過去のメッセージの表示
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ユーザー入力の処理
    if user_query := st.chat_input("話したいことは何ですか？"):
        # ユーザーメッセージを表示
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.write(user_query)

    # エージェントの実行と回答の表示
    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            response = agent.invoke(
                {"input": user_query},
                config={"configurable": {"thread_id": st.session_state["thread_id"]}},
            )
            st.write(response["output"])
            st.session_state.messages.append(
                {"role": "assistant", "content": response["output"]}
            )

if __name__ == "__main__":
    main()
