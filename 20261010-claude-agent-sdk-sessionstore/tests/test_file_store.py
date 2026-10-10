import pytest
from claude_agent_sdk.testing import run_session_store_conformance

from verify.file_store import FileSessionStore

pytestmark = pytest.mark.anyio


async def test_file_store_conformance(tmp_path):
    n = 0

    def make():
        nonlocal n
        n += 1
        return FileSessionStore(tmp_path / f"s{n}")

    await run_session_store_conformance(make)
