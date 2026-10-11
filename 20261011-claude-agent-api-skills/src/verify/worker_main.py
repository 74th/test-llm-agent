"""self-hosted environment のワーカー(コンテナ内で実行する)。

ANTHROPIC_ENVIRONMENT_ID / ANTHROPIC_ENVIRONMENT_KEY だけを使う。Anthropic の API キーは渡さない。
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

from anthropic import AsyncAnthropic
from anthropic.lib.environments import EnvironmentWorker

WORKDIR = "/workspace"


async def main() -> None:
    env_id = os.environ.get("ANTHROPIC_ENVIRONMENT_ID")
    env_key = os.environ.get("ANTHROPIC_ENVIRONMENT_KEY")
    if not env_id or not env_key:
        sys.exit("ANTHROPIC_ENVIRONMENT_ID と ANTHROPIC_ENVIRONMENT_KEY を設定してください")
    worker = EnvironmentWorker(AsyncAnthropic(), environment_id=env_id, environment_key=env_key, workdir=WORKDIR)
    task = asyncio.ensure_future(worker.run())
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
