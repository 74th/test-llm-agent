import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from verify.config import MODEL, sdk_env

pytestmark = pytest.mark.anyio


async def test_haiku_roundtrip():
    result = None
    async for m in query(
        prompt="OKとだけ答えて",
        options=ClaudeAgentOptions(model=MODEL, env=sdk_env(), max_turns=1, max_budget_usd=0.1),
    ):
        if isinstance(m, ResultMessage):
            result = m
    assert result is not None and not result.is_error, result
    assert result.result
