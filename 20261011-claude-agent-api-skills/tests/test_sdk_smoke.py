"""実行ヘルパーのスモーク(live)。"""

import pytest

from verify.config import MODEL
from verify.sandboxd import SandboxdClient
from verify.sdk_agent import run_condition

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_plain_request_uses_haiku_and_sandbox():
    with SandboxdClient() as c:
        if not c.health():
            pytest.skip("sandboxd が起動していない")
        rr = await run_condition("plain", "sandbox_exec で `hostname` を実行して、結果だけを答えて。", c)
    assert rr.models and all(m.startswith(MODEL) for m in rr.models), rr.models
    assert rr.tool_names and set(rr.tool_names) <= {"mcp__sandbox__sandbox_exec"}
    assert rr.sandbox_calls and rr.sandbox_calls[0].result["exit_code"] == 0
    assert rr.cost_usd is not None and rr.cost_usd < 0.2
    print(rr.init, rr.final_text, rr.cost_usd)
