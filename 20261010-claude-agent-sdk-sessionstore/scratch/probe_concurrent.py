import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import ClaudeSDKClient
from verify.background import *
from verify.agent import new_config_dir
async def main():
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), Path("workspace"))) as c:
        async def reader():           # 受信専用タスク。ずっと読み続ける
            async for m in c.receive_messages():
                rec.record(m)
        r = asyncio.create_task(reader())
        await c.query("バックグラウンドで `sleep 30; echo hi` を実行して。完了を待たずすぐ返答して。")
        await asyncio.sleep(8)
        await c.query("追加の指示: 7かける8は? 数字だけ。")   # 読み取り中に別タスクから送信
        await asyncio.sleep(40)
        r.cancel()
    for e in rec.events:
        if e.kind in ("result","assistant") and e.detail: print(e.t, e.kind, e.origin, e.detail[:60])
asyncio.run(main())
