import asyncio, sys
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import ClaudeSDKClient
from verify.background import *
from verify.agent import new_config_dir
async def main():
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), Path("workspace"))) as c:
        await c.query("バックグラウンドで `sleep 15; echo hi` を実行して。完了を待たずすぐ返答して。")
        await drain_until(c, rec, until=lambda r: len(r.results)>=2, timeout=80)
    for e in rec.events:
        if e.kind.startswith("system:") and "thinking" not in e.kind: print(e.t, e.kind, e.detail[:110])
        elif e.kind=="result": print(e.t,"RESULT",e.origin)
asyncio.run(main())
