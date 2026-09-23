from typing import Literal

import pytest
from langchain.tools import tool

from create_agent import create_agent_instance


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


def _print_streaming_response(agent, message: str, label: str) -> None:
    print(f"{label}:", end=" ", flush=True)

    stream = agent.stream(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": "test_thread_id"}},
        stream_mode="messages",
    )
    try:
        for chunk, metadata in stream:
            if metadata.get("langgraph_node") != "model":
                continue

            content = _chunk_to_text(chunk.content)
            if not content:
                continue

            print(content, end="", flush=True)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    print()


def test_agent():
    print("==== TEST: test_agent ====")
    QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""

    agent = create_agent_instance(instructions=QUESTIONER_INSTRUCTIONS, reasoning=False)

    _print_streaming_response(agent, "日本の鳥について教えて", "1")
    _print_streaming_response(agent, "海に生息するものについて教えて", "2")


def test_agent_tool():
    print("==== TEST: test_agent_tool ====")

    @tool
    def control_aircon_on(mode: Literal["warm", "cool"]) -> str:
        """エアコンをオンにします。暖房はwarm、冷房はcoolを指定してください。"""
        print(f"エアコンを{mode}モードでオンにします")
        return f"エアコンを{mode}モードでオンにしました"

    @tool
    def control_aircon_off() -> str:
        """エアコンをオフにします"""
        print("エアコンをオフにします")
        return "エアコンをオフにしました"

    instructions = """
あなたは自宅にいる音声AIアシスタントです。
エアコンの操作を行うには、 control_aircon_on と control_aircon_off というツールを使ってください。
音声アシスタントであるため、マークダウン等の表現は使わず、3文程度の文章で答えてください。
家電操作ツールを実行した場合には、短く1文程度で答えてください。
"""

    agent = create_agent_instance(instructions=instructions, reasoning=False, tools=[control_aircon_on, control_aircon_off])

    _print_streaming_response(agent, "エアコンを暖房にして", "1")

    _print_streaming_response(agent, "今日の夕飯に、豚バラ肉が余っているのだけれど、中華で何がいいかな", "1")
