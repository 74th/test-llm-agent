from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from llama_reasoning_chat import LlamaServerReasoningChatModel


def create_agent_instance(instructions: str, reasoning: bool, tools: list = []) ->CompiledStateGraph:
    if not reasoning:
        extra_body = {
            "chat_template_kwargs": {"enable_thinking": False},
        }
    else:
        extra_body = {}

    model = LlamaServerReasoningChatModel(
        base_url="http://constance:30323/v1",
        api_key="dummy",
        model="gemma4:26b",
        extra_body=extra_body,
    )

    return create_agent(
        model=model,
        tools=tools,
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
