"""SessionStore 差し替え時の resume 検証(spec: session-store-resume)。"""

import json
from pathlib import Path

import pytest
from claude_agent_sdk import InMemorySessionStore

from verify import jev
from verify.agent import new_config_dir, run_turn
from verify.file_store import FileSessionStore

pytestmark = pytest.mark.anyio

CWD = Path(__file__).resolve().parents[1] / "workspace"


@pytest.fixture(autouse=True)
def _cwd():
    CWD.mkdir(exist_ok=True)


async def first_turn(store, issued):
    t = await run_turn(
        "issue_token ツールで認証トークンを発行してください。",
        store=store,
        issued=issued,
        config_dir=new_config_dir(),
        cwd=CWD,
    )
    assert t.result and not t.result.is_error, t.result
    assert issued, "tool が呼ばれていない"
    return t


async def check_resume(store, issued, first):
    token = issued[0]
    # 前提: 先行の返答に値は出ていない
    assert token not in first.text, f"前提不成立: 返答に値が出た: {first.text!r}"
    # 別の config dir(= ローカル transcript なし)から resume
    second = await run_turn(
        "先ほど issue_token が返したトークンの値を、そのまま答えてください。",
        store=store,
        resume=first.session_id,
        issued=issued,
        config_dir=new_config_dir(),
        cwd=CWD,
    )
    assert second.result and not second.result.is_error, second.result
    return second


async def test_inmemory_store_resume():
    store, issued = InMemorySessionStore(), []
    first = await first_turn(store, issued)
    second = await check_resume(store, issued, first)
    assert issued[0] in second.text
    assert len(issued) == 1, "tool が再実行された(参照ではなく再発行)"


async def test_file_store_resume(tmp_path):
    issued = []
    first = await first_turn(FileSessionStore(tmp_path / "s"), issued)
    # 新しいインスタンス(プロセス再起動相当)で復元
    second = await check_resume(FileSessionStore(tmp_path / "s"), issued, first)
    assert issued[0] in second.text
    assert len(issued) == 1


async def test_store_contains_tool_result(tmp_path):
    from claude_agent_sdk import SessionKey
    from claude_agent_sdk._internal.sessions import project_key_for_directory

    store, issued = FileSessionStore(tmp_path / "s"), []
    first = await first_turn(store, issued)
    key: SessionKey = {
        "project_key": project_key_for_directory(str(CWD)),
        "session_id": first.session_id,
    }
    entries = await store.load(key)
    assert entries, "ストアが空"
    assert issued[0] in json.dumps(entries, ensure_ascii=False)


async def test_resume_judged_by_jev(tmp_path):
    issued = []
    store = FileSessionStore(tmp_path / "s")
    first = await first_turn(store, issued)
    second = await check_resume(store, issued, first)
    assert jev.passes(jev.mentions_value(second.text, issued[0]))
    assert not jev.passes(jev.mentions_value(first.text, issued[0]))


async def test_negative_control_empty_store(tmp_path):
    """対照実験: ストアが空で config dir も別なら、値を参照できない(ストア依存の証明)。"""
    issued = []
    first = await first_turn(FileSessionStore(tmp_path / "a"), issued)
    try:
        second = await run_turn(
            "先ほど issue_token が返したトークンの値を、そのまま答えてください。",
            store=FileSessionStore(tmp_path / "empty"),
            resume=first.session_id,
            issued=issued,
            config_dir=new_config_dir(),
            cwd=CWD,
        )
    except Exception:
        return  # 復元不能で失敗するのも期待どおり
    assert issued[0] not in second.text
