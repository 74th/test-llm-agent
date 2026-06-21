import uuid

import streamlit as st

from create_agent import create_agent_instance

# 2つのエージェントのための指示（プロンプト）
QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""


def check_weather(location: str) -> str:
    """Return the weather forecast for the specified location."""
    return f"It's always sunny in {location}"


def _chunk_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        return "".join(texts)

    return ""


def _stream_agent_response(agent, user_query: str, thread_id: str):
    stream = agent.stream(
        {"messages": [{"role": "user", "content": user_query}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="messages",
    )
    try:
        for chunk, metadata in stream:
            if metadata.get("langgraph_node") != "model":
                continue

            content = _chunk_to_text(chunk.content)
            if content:
                yield content
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def main():
    if st.session_state.get("agent") is None:
        agent = create_agent_instance(QUESTIONER_INSTRUCTIONS, False)
        st.session_state.agent = agent
    else:
        agent = st.session_state.agent

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
                content = st.write_stream(
                    _stream_agent_response(
                        agent,
                        user_query,
                        st.session_state["thread_id"],
                    )
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": content or ""}
                )


if __name__ == "__main__":
    main()
