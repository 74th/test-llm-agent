import asyncio, sys, json
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import InMemorySessionStore
from claude_agent_sdk._internal.sessions import project_key_for_directory
from verify.agent import *

WINDOW = sys.argv[1] if len(sys.argv) > 1 else "25000"
async def main():
    cwd = Path("workspace").resolve(); store = InMemorySessionStore(); issued = []
    env = json.loads(WINDOW) if WINDOW.startswith("{") else {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": WINDOW}
    t = await run_turn("issue_token ツールで認証トークンを発行してください。", store=store, issued=issued, config_dir=new_config_dir(), cwd=cwd, env_extra=env)
    sid = t.session_id
    key = {"project_key": project_key_for_directory(str(cwd)), "session_id": sid}
    def boundaries(es): return [i for i, e in enumerate(es) if e.get("subtype") == "compact_boundary"]
    cost = 0.0
    for i in range(1, 13):
        t = await run_turn(f"[{i}] 日本語で、{i}番目の話題として、適当な豆知識を2500字程度で書いてください。", store=store, resume=sid, issued=issued, config_dir=new_config_dir(), cwd=cwd, env_extra=env)
        cost += (t.result.total_cost_usd or 0)
        es = await store.load(key)
        u = t.result.usage or {}
        print(i, "entries", len(es), "boundaries", boundaries(es), "input_tok", u.get("input_tokens"), "cache_read", u.get("cache_read_input_tokens"), f"cost so far ${cost:.3f}")
        if boundaries(es): break
    es = await store.load(key); b = boundaries(es)
    if not b: print("compaction did not trigger"); return
    print("--- post-boundary entries ---")
    for e in es[b[0]:]:
        if e.get("type") in ("user", "assistant", "system"):
            m = e.get("message", {}); c = m.get("content") if isinstance(m, dict) else None
            s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            print(e["type"], e.get("subtype"), "SUMMARY" if e.get("isCompactSummary") else "", "|", (s or "")[:120].replace("\n", " "), "| token:", issued[0] in json.dumps(e, ensure_ascii=False))
    t = await run_turn("最初に issue_token が返したトークンの値を、そのまま答えてください。", store=store, resume=sid, issued=issued, config_dir=new_config_dir(), cwd=cwd, env_extra=env)
    print("answer:", t.text[:150], "| ok:", issued[0] in t.text)
asyncio.run(main())
