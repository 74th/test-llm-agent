from starlette.testclient import TestClient
from claude_agent_sdk import ResultMessage, StreamEvent
from poc.adapter import ClaudeAgUiAdapter
from poc.app import create_app

async def sdk_stream(**_):
    yield StreamEvent("1", "session-x", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "前半"}})
    yield StreamEvent("2", "session-x", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "後半"}})
    yield ResultMessage("success", 3, 2, False, 1, "session-x")

def test_thread_api_and_sse_persist_completed_message(tmp_path):
    app = create_app(tmp_path / "api.sqlite3", ClaudeAgUiAdapter(sdk_stream))
    with TestClient(app) as client:
        thread = client.post("/threads", json={"title": "検証"}).json()
        response = client.post("/agent/run", json={"threadId": thread["id"], "runId": "run-x", "messages": [{"id": "user-x", "role": "user", "content": "こんにちは"}]})
        assert response.status_code == 200
        assert response.text.index("RUN_STARTED") < response.text.index("TEXT_MESSAGE_CONTENT") < response.text.index("RUN_FINISHED")
        restored = client.get(f"/threads/{thread['id']}").json()
    assert restored["lastRunStatus"] == "completed"
    assert [item["content"] for item in restored["messages"]] == ["こんにちは", "前半後半"]
    assert restored["agentSessionId"] == "session-x"
