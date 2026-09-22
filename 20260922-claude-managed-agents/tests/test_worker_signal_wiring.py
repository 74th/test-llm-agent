"""SIGINT/SIGTERM must cancel the worker task, not kill the process.

Exercises `worker.__main__._run_cancellable` directly against a coroutine
that would otherwise block for a long time, so the test doesn't need a real
Anthropic environment (which `EnvironmentWorker.run()` requires).
"""

import asyncio
import os
import signal

import pytest

from worker.__main__ import _run_cancellable


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_cancels_task_instead_of_hanging(sig):
    cancelled = False

    async def never_finishes_on_its_own():
        nonlocal cancelled
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled = True
            raise

    async def main():
        task = asyncio.ensure_future(_run_cancellable(never_finishes_on_its_own))
        await asyncio.sleep(0.05)
        os.kill(os.getpid(), sig)
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(main())
    assert cancelled
