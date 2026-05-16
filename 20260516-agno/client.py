import asyncio
import uuid

from agno.client import AgentOSClient
from agno.run.agent import RunCompletedEvent, RunContentEvent


async def main_stream():
    # Connect to AgentOS
    client = AgentOSClient(base_url="http://localhost:8000")

    # Get configuration
    config = await client.aget_config()

    session_id : None | str = None
    async for event in client.run_agent_stream(
        agent_id="workbench",
        message="こんにちは。文鳥のかわいさについて語ってください。",
    ):
        session_id = event.session_id
        if isinstance(event, RunContentEvent) and event.content:
            print(event.content, end="", flush=True)
        elif isinstance(event, RunCompletedEvent):
            print(f"\nRun ID: {event.run_id}")

    print("session_id:", session_id)

    async for event in client.run_agent_stream(
        agent_id="workbench",
        message="飼うことはできる？",
        session_id=session_id,
    ):
        if isinstance(event, RunContentEvent) and event.content:
            print(event.content, end="", flush=True)
        elif isinstance(event, RunCompletedEvent):
            print(f"\nRun ID: {event.run_id}")


async def main_blocking():
    # Connect to AgentOS
    client = AgentOSClient(base_url="http://localhost:8000")

    # Get configuration
    config = await client.aget_config()

    session_id : None | str = None
    result = await client.run_agent(
        agent_id="workbench",
        message="こんにちは。文鳥のかわいさについて語ってください。",
    )
    print(result.content)
    print(result.session_id)

    result = await client.run_agent(
        agent_id="workbench",
        message="飼うことはできる？",
        session_id=result.session_id,
    )
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main_stream())
