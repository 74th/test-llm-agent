"""Entrypoint for the self-hosted environment worker container.

Two subcommands, one image (see design.md D4):

- `run`         — mode A: poll the work queue forever in this same process
                  (`EnvironmentWorker.run()`).
- `handle-item` — mode B: service the single work item this container was
                  launched for, then exit (`EnvironmentWorker.handle_item()`).
                  IDs and the per-item secret are read from the forwarded
                  `ANTHROPIC_*` environment variables.

Both run under `workdir="/workspace"`. SIGINT/SIGTERM cancel the asyncio task
running the worker (so `EnvironmentWorker` can finish in-flight work and, for
`handle-item`, upload before exiting) rather than killing the process.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys

from anthropic import AsyncAnthropic
from anthropic.lib.environments import EnvironmentWorker

WORKDIR = "/workspace"


def _worker_for_run() -> EnvironmentWorker:
    environment_id = os.environ.get("ANTHROPIC_ENVIRONMENT_ID")
    environment_key = os.environ.get("ANTHROPIC_ENVIRONMENT_KEY")
    if not environment_id or not environment_key:
        sys.exit(
            "ANTHROPIC_ENVIRONMENT_ID と ANTHROPIC_ENVIRONMENT_KEY の両方を設定してください "
            "(mode A の常駐ワーカーはポーリングに両方を使う)。"
        )
    return EnvironmentWorker(
        AsyncAnthropic(),
        environment_id=environment_id,
        environment_key=environment_key,
        workdir=WORKDIR,
    )


def _worker_for_handle_item() -> EnvironmentWorker:
    # No explicit IDs: EnvironmentWorker.handle_item() reads
    # ANTHROPIC_SESSION_ID / ANTHROPIC_WORK_ID / ANTHROPIC_ENVIRONMENT_ID /
    # ANTHROPIC_WORK_SECRET (falling back to ANTHROPIC_ENVIRONMENT_KEY) from
    # the environment itself.
    return EnvironmentWorker(AsyncAnthropic(), workdir=WORKDIR)


async def _run_cancellable(coro_factory) -> None:
    task = asyncio.ensure_future(coro_factory())
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass


async def cmd_run() -> None:
    await _run_cancellable(_worker_for_run().run)


async def cmd_handle_item() -> None:
    await _run_cancellable(_worker_for_handle_item().handle_item)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="worker")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Poll the environment work queue forever (mode A).")
    sub.add_parser(
        "handle-item",
        help="Service one already-claimed work item and exit (mode B).",
    )
    args = parser.parse_args(argv)

    if args.command == "run":
        asyncio.run(cmd_run())
    elif args.command == "handle-item":
        asyncio.run(cmd_handle_item())


if __name__ == "__main__":
    main()
