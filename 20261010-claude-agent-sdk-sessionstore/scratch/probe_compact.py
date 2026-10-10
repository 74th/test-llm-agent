import asyncio, sys, json, tempfile
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import InMemorySessionStore
from claude_agent_sdk._internal.sessions import project_key_for_directory
from verify.agent import *

async def main():
    cwd = Path("workspace").resolve(); store = InMemorySessionStore(); issued = []
    t1 = await run_turn("issue_token ツールで認証トークンを発行してください。", store=store, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    key = {"project_key": project_key_for_directory(str(cwd)), "session_id": t1.session_id}
    before = await store.load(key)
    print("before /compact: entries =", len(before))
    t2 = await run_turn("/compact", store=store, resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    print("compact result:", repr(t2.result.result[:150]) if t2.result else None)
    after = await store.load(key)
    print("after /compact: entries =", len(after))
    for i, e in enumerate(after[len(before):]):
        s = json.dumps(e, ensure_ascii=False)
        print(i, e.get("type"), e.get("subtype"), "isCompactSummary=", e.get("isCompactSummary"), "| token in entry:", issued[0] in s, "|", s[:130])
    # 既存 entry は消えず残っているか
    print("pre-compaction entries still in store:", after[:len(before)] == before, " token in raw store:", issued[0] in json.dumps(after))
    t3 = await run_turn("先ほど issue_token が返したトークンの値を、そのまま答えてください。", store=store, resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    print("after-compact resume answer:", t3.text, "| ok:", issued[0] in t3.text, "| reissued:", len(issued) > 1)
asyncio.run(main())
