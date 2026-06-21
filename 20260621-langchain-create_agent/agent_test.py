import pytest

from create_agent import create_agent_instance

QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""


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

    for chunk, metadata in agent.stream(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": "test_thread_id"}},
        stream_mode="messages",
    ):
        if metadata.get("langgraph_node") != "model":
            continue

        content = _chunk_to_text(chunk.content)
        if not content:
            continue

        print(content, end="", flush=True)

    print()


def test_agent():
    print("==== TEST: test_agent ====")

    agent = create_agent_instance(instructions=QUESTIONER_INSTRUCTIONS, reasoning=False)

    _print_streaming_response(agent, "日本の鳥について教えて", "1")
    _print_streaming_response(agent, "海に生息するものについて教えて", "2")
