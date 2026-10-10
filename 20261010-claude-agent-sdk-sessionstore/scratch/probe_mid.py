import asyncio, sys
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import ClaudeSDKClient
from verify.background import *
from verify.agent import new_config_dir
async def main():
    cwd = Path("workspace"); rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), cwd)) as c:
        await c.query("バックグラウンドで `sleep 40; echo DONE-VALUE=ZX4091` を実行して。完了を待たずすぐ返答して。")
        await drain_until(c, rec, until=lambda r: len(r.results)>=1, timeout=90)
        await c.query("待っている間に質問: 7かける8はいくつ?数字だけ答えて。")
        await drain_until(c, rec, until=lambda r: len(r.results)>=2, timeout=60)
        print("mid-wait answered at", rec.events[-1].t, rec.events[-1].detail)
        await drain_until(c, rec, until=lambda r: len(r.results)>=3, timeout=90)
    for e in rec.events:
        if e.kind in("result","assistant"): print(e.t,e.kind,e.origin,e.detail[:90])
asyncio.run(main())
