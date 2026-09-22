"""Mode B orchestrator (design.md D2/D3).

Polls the self-hosted environment's work queue with the mid-level poller and
launches one throwaway `docker run <image> handle-item` container per
`session` work item. Container start/exit are recorded to the lifecycle log
(orchestrator/lifecycle_log.py). Non-session work items are skipped
untouched (no container, no stop call) - see § dispatch below.

Authentication: this process only ever needs the *environment key*, never
the org-wide `ANTHROPIC_API_KEY` - the work queue client is constructed with
`auth_token=environment_key` (self-hosted-environment: 組織スコープの API
キーはワーカーホストに置かない).
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from typing import Any

from anthropic import AsyncAnthropic

from common.config import EnvironmentWorkerConfig
from orchestrator.lifecycle_log import log_event

_STOP_REQUESTED = False

_IMAGE_START_FAILURE_MARKERS = (
    "unable to find image",
    "no such image",
    "manifest unknown",
    "pull access denied",
)


def _handle_stop_signal(signum: int, frame: Any) -> None:
    # Only sets a flag - never kills the in-flight `docker run` subprocess,
    # so its container_exit event is always written before the orchestrator
    # actually stops (container-lifecycle-log: オーケストレータが停止しても
    # 対応が崩れない).
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)


def container_name_for(work_id: str) -> str:
    return f"cma-{work_id}"


def build_docker_run_command(
    image: str,
    *,
    container_name: str,
    forwarded_secret_env: list[str],
    gcp_key_path: str | None,
) -> list[str]:
    """Build the `docker run` argv for one throwaway session container.

    Secrets are passed as value-less `-e KEY` so the value comes from this
    process's own environment, never appearing in the command line or in
    `docker ps` / `docker inspect` output (self-hosted-environment: 秘密情報
    がログに出ない). `/workspace` is intentionally not mounted (mode B has
    no persisted workspace - see design.md D4).
    """
    cmd = ["docker", "run", "--rm", "--name", container_name]
    for key in forwarded_secret_env:
        cmd += ["-e", key]
    if gcp_key_path:
        cmd += [
            "-v",
            f"{gcp_key_path}:/run/secrets/gcp-sa-key.json:ro",
            "-e",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ]
    cmd += [image, "handle-item"]
    return cmd


def _is_start_failure(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _IMAGE_START_FAILURE_MARKERS)


def run_one_work_item(
    image: str,
    work: Any,
    environment_key: str,
    gcp_key_path: str | None,
) -> None:
    session_id = work.data.id
    work_id = work.id
    environment_id = work.environment_id
    container_name = container_name_for(work_id)

    common_fields = {
        "session_id": session_id,
        "work_id": work_id,
        "environment_id": environment_id,
        "container_name": container_name,
    }

    child_env = dict(os.environ)
    child_env["ANTHROPIC_SESSION_ID"] = session_id
    child_env["ANTHROPIC_WORK_ID"] = work_id
    child_env["ANTHROPIC_ENVIRONMENT_ID"] = environment_id
    child_env["ANTHROPIC_ENVIRONMENT_KEY"] = environment_key
    child_env["ANTHROPIC_WORK_SECRET"] = work.secret or ""
    if gcp_key_path:
        child_env["GOOGLE_APPLICATION_CREDENTIALS"] = "/run/secrets/gcp-sa-key.json"

    forwarded_secret_env = [
        "ANTHROPIC_SESSION_ID",
        "ANTHROPIC_WORK_ID",
        "ANTHROPIC_ENVIRONMENT_ID",
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_WORK_SECRET",
    ]
    cmd = build_docker_run_command(
        image,
        container_name=container_name,
        forwarded_secret_env=forwarded_secret_env,
        gcp_key_path=gcp_key_path,
    )

    # --- workspace restore hook (not implemented in this change) ---
    # This is where a future workspace-persistence feature would restore
    # `session_id`'s saved workspace into a host directory and bind-mount it
    # at /workspace before `docker run`, so mode B's throwaway container
    # picks up where the previous turn's container left off (see 6.9 / the
    # proposal's persistence goal). Deliberately absent here: this change
    # only confirms the start/exit events exist, not persistence itself.

    log_event("container_start", **common_fields)
    start = time.monotonic()

    # try/finally-adjacent: every path below writes exactly one terminal
    # event, whether the container ran and exited, or `docker run` itself
    # never managed to start it (bad image, etc.).
    proc = subprocess.run(cmd, env=child_env, capture_output=True, text=True)
    duration_ms = int((time.monotonic() - start) * 1000)

    if proc.returncode != 0 and _is_start_failure(proc.stderr):
        log_event(
            "container_start_failed",
            **common_fields,
            error=proc.stderr.strip()[:2000],
        )
        return

    # --- workspace save hook (not implemented in this change) ---
    # This is where a future workspace-persistence feature would read back
    # whatever the just-exited container left in its (currently unmounted)
    # /workspace and save it for `session_id`'s next turn to restore above.
    # Requires mounting /workspace to a host path first, which this change
    # deliberately does not do (see 6.9).

    error = None if proc.returncode == 0 else f"non-zero exit code {proc.returncode}: {proc.stderr.strip()[:2000]}"
    log_event(
        "container_exit",
        **common_fields,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        error=error,
    )


async def drain_work_queue(
    *,
    client: AsyncAnthropic,
    environment_id: str,
    environment_key: str,
    image: str,
    gcp_key_path: str | None,
    drain: bool,
) -> None:
    async for work in client.beta.environments.work.poller(
        environment_id=environment_id,
        environment_key=environment_key,
        block_ms=None if drain else 500,
        reclaim_older_than_ms=2000,
        drain=drain,
        auto_stop=False,
    ):
        if work.data.type != "session":
            # Not ours to run a container for - leave it exactly alone.
            continue

        run_one_work_item(image, work, environment_key, gcp_key_path)

        if _STOP_REQUESTED:
            break


async def async_main(args: argparse.Namespace) -> None:
    cfg = EnvironmentWorkerConfig.load()
    install_signal_handlers()

    async with AsyncAnthropic(auth_token=cfg.environment_key) as client:
        await drain_work_queue(
            client=client,
            environment_id=cfg.environment_id,
            environment_key=cfg.environment_key,
            image=args.image,
            gcp_key_path=args.gcp_key,
            drain=args.drain,
        )


def main(argv: list[str] | None = None) -> None:
    import asyncio

    parser = argparse.ArgumentParser(prog="orchestrator")
    parser.add_argument("--image", default=os.environ.get("CMA_WORKER_IMAGE", "cma-verify-worker:dev"))
    parser.add_argument("--gcp-key", default=os.environ.get("CMA_GCP_KEY_PATH"))
    parser.add_argument(
        "--drain",
        action="store_true",
        help="Stop once the work queue is empty instead of polling forever.",
    )
    args = parser.parse_args(argv)
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
