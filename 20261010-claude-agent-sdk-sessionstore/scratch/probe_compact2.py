import asyncio, sys, json
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import InMemorySessionStore
from claude_agent_sdk._internal.sessions import project_key_for_directory
from verify.agent import *
async def main():
    cwd = Path("workspace").resolve(); store = InMemorySessionStore(); issued = []
    t1 = await run_turn("issue_token ツールで認証トークンを発行してください。", store=store, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    key = {"project_key": project_key_for_directory(str(cwd)), "session_id": t1.session_id}
    n = len(await store.load(key))
    await run_turn("/compact", store=store, resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    new = (await store.load(key))[n:]
    for e in new:
        if e.get("type") in ("user","assistant","system"):
            msg = e.get("message", {}); c = msg.get("content") if isinstance(msg, dict) else None
            s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            print(e["type"], e.get("subtype"), "summary" if e.get("isCompactSummary") else "", "|", (s or "")[:400].replace("\n"," "))
            print("   token in:", issued[0] in json.dumps(e, ensure_ascii=False))
asyncio.run(main())
