import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import ClaudeSDKClient
from verify.background import *
from verify.agent import new_config_dir

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 40

async def main():
    cwd = Path("workspace"); cwd.mkdir(exist_ok=True)
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), cwd)) as c:
        await c.query(f"バックグラウンドで `sleep {SECS}; echo DONE-VALUE=ZX{SECS}91` を実行して。完了を待たず、すぐ返答して。")
        # 最初の result まで
        await drain_until(c, rec, until=lambda r: len(r.results) >= 1, timeout=90)
        print("first result at", rec.events[-1].t)
        # 完了+余裕を待って、追加の result/assistant が来るか
        ok = await drain_until(c, rec, until=lambda r: len(r.results) >= 2, timeout=SECS + 60)
        print("second result:", ok)
    for e in rec.events: print(e)
asyncio.run(main())
