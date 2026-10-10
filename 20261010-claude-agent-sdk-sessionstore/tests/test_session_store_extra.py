"""SessionStore の追加検証: サブエージェント transcript とコンパクション(spec: session-store-resume)。"""

import json
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    InMemorySessionStore,
    ResultMessage,
    TextBlock,
    query,
)
from claude_agent_sdk._internal.sessions import project_key_for_directory

from verify.agent import TOOL_NAME, make_probe_server, new_config_dir, run_turn
from verify.config import MODEL, sdk_env
from verify.file_store import FileSessionStore

pytestmark = pytest.mark.anyio

CWD = Path(__file__).resolve().parents[1] / "workspace"
RESULTS = Path(__file__).resolve().parents[1] / "results"


@pytest.fixture(autouse=True)
def _dirs():
    CWD.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)


async def run_parent(prompt, store, issued, resume=None):
    opts = ClaudeAgentOptions(
        model=MODEL,
        env=sdk_env(new_config_dir()),
        system_prompt="あなたは検証用の親エージェントです。トークン発行は必ず worker サブエージェントに任せ、自分では issue_token を呼びません。",
        mcp_servers={"probe": make_probe_server(issued)},
        agents={
            "worker": AgentDefinition(
                description="トークンを発行する作業者",
                prompt="issue_token ツールを1回だけ呼び、返ってきた値を報告せよ。",
                tools=[TOOL_NAME],
                model="haiku",
            )
        },
        allowed_tools=[TOOL_NAME, "Agent", "Task"],
        tools=["Agent"],
        permission_mode="bypassPermissions",
        setting_sources=[],
        max_turns=8,
        max_budget_usd=0.3,
        session_store=store,
        resume=resume,
        cwd=CWD,
    )
    text, sid = "", None
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, AssistantMessage):
            text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        if isinstance(m, ResultMessage):
            sid = m.session_id
    return sid, text


async def test_subagent_transcript_is_mirrored_and_resumable(tmp_path):
    issued = []
    store = FileSessionStore(tmp_path / "s")
    sid, _ = await run_parent("worker サブエージェントにトークンを発行させてください。", store, issued)
    assert issued, "サブエージェント経由で tool が呼ばれていない"
    pk = project_key_for_directory(str(CWD))
    subkeys = await store.list_subkeys({"project_key": pk, "session_id": sid})
    assert subkeys and all(k.startswith("subagents/") for k in subkeys)
    entries = await store.load({"project_key": pk, "session_id": sid, "subpath": subkeys[0]})
    assert entries and issued[0] in json.dumps(entries)
    # 新しいストアインスタンス + 別 config dir で resume
    _, text = await run_parent("worker が発行したトークンの値を、そのまま答えてください。", FileSessionStore(tmp_path / "s"), issued, resume=sid)
    assert issued[0] in text
    assert len(issued) == 1


async def test_compaction_entries_are_stored():
    """/compact 後: 要約 entry と境界がストアに追記され、圧縮前の raw entry も残る。"""
    store, issued = InMemorySessionStore(), []
    t1 = await run_turn("issue_token ツールで認証トークンを発行してください。", store=store, issued=issued, config_dir=new_config_dir(), cwd=CWD)
    key = {"project_key": project_key_for_directory(str(CWD)), "session_id": t1.session_id}
    before = await store.load(key)
    await run_turn("/compact", store=store, resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=CWD)
    after = await store.load(key)
    assert after[: len(before)] == before, "圧縮前の entry が失われた"
    new = after[len(before):]
    assert any(e.get("subtype") == "compact_boundary" for e in new)
    summaries = [e for e in new if e.get("isCompactSummary")]
    assert summaries, "要約 entry がストアに無い"
    # 圧縮後の復元は、要約が値を保持しているかに依存する(これは観測であり、成否は固定しない)
    t3 = await run_turn("先ほど issue_token が返したトークンの値を、そのまま答えてください。", store=store, resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=CWD)
    (RESULTS / "compaction_finding.json").write_text(json.dumps({
        "summary_contains_token": issued[0] in json.dumps(summaries, ensure_ascii=False),
        "raw_store_contains_token": issued[0] in json.dumps(after, ensure_ascii=False),
        "answer_after_compaction_has_token": issued[0] in t3.text,
        "answer": t3.text,
    }, ensure_ascii=False, indent=2))
