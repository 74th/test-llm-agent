"""サンドボックス用 tool の単体テスト(API キー不要。sandboxd を起動しておく)。"""

import pytest

from verify.sandboxd import SandboxdClient
from verify.sdk_agent import PathMapper, make_sandbox_server

pytestmark = pytest.mark.anyio
HOST = "/tmp/skill-verify-abc/project"


def test_path_mapper():
    m = PathMapper(HOST)
    assert m(f"python3 {HOST}/.claude/skills/x/scripts/p.py") == "python3 /workspace/.claude/skills/x/scripts/p.py"
    assert m("/etc/sandbox-marker") == "/etc/sandbox-marker"


@pytest.fixture
def tools():
    c = SandboxdClient()
    if not c.health():
        pytest.skip("sandboxd が起動していない")
    log = []
    _, ts = make_sandbox_server(c, PathMapper(HOST), log)
    yield {t.name: t for t in ts}, log, c
    c.close()


async def test_exec_maps_and_records(tools):
    ts, log, _ = tools
    out = await ts["sandbox_exec"].handler({"command": f"echo {HOST}/a && pwd"})
    text = out["content"][0]["text"]
    assert "/workspace/a" in text and HOST not in text
    assert log[-1].tool == "sandbox_exec"
    assert log[-1].raw["command"].startswith(f"echo {HOST}")
    assert log[-1].mapped["command"].startswith("echo /workspace/a")
    assert log[-1].replaced and log[-1].result["exit_code"] == 0


async def test_read_and_list(tools):
    ts, log, c = tools
    c.write("/workspace/tooltest/f.txt", "hello")
    out = await ts["sandbox_read_file"].handler({"path": f"{HOST}/tooltest/f.txt"})
    assert out["content"][0]["text"] == "hello"
    assert log[-1].mapped == {"path": "/workspace/tooltest/f.txt"}
    out = await ts["sandbox_list_dir"].handler({"path": "/workspace/tooltest"})
    assert "f.txt" in out["content"][0]["text"] and not log[-1].replaced
    out = await ts["sandbox_read_file"].handler({"path": "/workspace/tooltest/none"})
    assert out.get("is_error") and "404" in out["content"][0]["text"]
    c.delete("/workspace/tooltest")
