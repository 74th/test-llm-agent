import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import query
from verify.background import *
from verify.agent import new_config_dir
async def main():
    cwd = Path("workspace"); rec = Recorder()
    async for m in query(prompt="バックグラウンドで `sleep 20; echo DONE-VALUE=ZX2091` を実行して。完了を待たずすぐ返答して。", options=bg_options(new_config_dir(), cwd)):
        rec.record(m)
    print("query() ended at", round(time.monotonic()-rec.t0,1), "results:", len(rec.results))
    for e in rec.events:
        if not e.kind.startswith("system:thinking"): print(e.t, e.kind, e.origin, e.detail[:90])
asyncio.run(main())
