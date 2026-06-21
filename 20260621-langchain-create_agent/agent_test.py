import pytest

from create_agent import create_agent_instance

QUESTIONER_INSTRUCTIONS = """あなたは好奇心旺盛な質問者です。相手の回答に対して、興味を持って頷くような反応をし、さらに深掘りするための質問を1つ投げかけてください。返答は音声化されるので、マークダウンや括弧などの表現は使わず、文章のみで答えてください。"""


def test_agent():
    print("==== TEST: test_agent ====")

    agent = create_agent_instance(instructions=QUESTIONER_INSTRUCTIONS, reasoning=False)

    res = agent.invoke(
        {"messages": [{"role": "user", "content": "日本の鳥について教えて"}]},
        config={"configurable": {"thread_id": "test_thread_id"}},
    )

    print("1:" ,res["messages"][-1].content)

    res = agent.invoke(
        {"messages": [{"role": "user", "content": "海に生息するものについて教えて"}]},
        config={"configurable": {"thread_id": "test_thread_id"}},
    )

    print("2:" ,res["messages"][-1].content)
