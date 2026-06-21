import uuid

import streamlit as st
from langchain_core.messages import HumanMessage

from create_agent import create_agent_instance

# 2つのエージェントのための指示（プロンプト）
QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""


def check_weather(location: str) -> str:
    """Return the weather forecast for the specified location."""
    return f"It's always sunny in {location}"


def main():
    agent = create_agent_instance(QUESTIONER_INSTRUCTIONS)
    # 3. Streamlit UIの実装
    st.title("AI エージェント")

    if "thread_id" not in st.session_state:
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
                    {"messages": [HumanMessage(content=user_query)]},
                    config={
                        "configurable": {"thread_id": st.session_state["thread_id"]}
                    },
                )
                content = response["messages"][-1].content
                st.write(content)
                st.session_state.messages.append(
                    {"role": "assistant", "content": content}
                )


if __name__ == "__main__":
    main()
