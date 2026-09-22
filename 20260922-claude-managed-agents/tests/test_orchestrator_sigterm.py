"""SIGTERM mid-item must not abandon the in-flight container's exit event.

Exercises the real signal handler (`orchestrator.main.install_signal_handlers`)
and the real `drain_work_queue` stop-after-current-item logic, with a fake
`subprocess.run` standing in for `docker run` (no live Anthropic credentials
or Docker daemon needed for this check - the mechanism under test is signal
handling, not Docker itself, which docker/2.1-2.4 already exercised directly).
"""

import asyncio
import json
import os
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import orchestrator.lifecycle_log as lifecycle_log
import orchestrator.main as orch


def make_work(work_id):
    return SimpleNamespace(
        id=work_id,
        environment_id="env1",
        secret="s",
        data=SimpleNamespace(id=f"session-{work_id}", type="session"),
    )


def test_sigterm_during_item_still_writes_container_exit_and_stops_after(tmp_path, monkeypatch):
    log_path = tmp_path / "log.jsonl"
    monkeypatch.setattr(lifecycle_log, "DEFAULT_LOG_PATH", log_path)
    orch._STOP_REQUESTED = False
    orch.install_signal_handlers()

    def fake_subprocess_run(*args, **kwargs):
        # Simulate: the signal arrives while `docker run` is still blocking.
        os.kill(os.getpid(), signal.SIGTERM)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    async def fake_poller(**kwargs):
        for w in [make_work("w1"), make_work("w2")]:
            yield w

    client = SimpleNamespace(
        beta=SimpleNamespace(environments=SimpleNamespace(work=SimpleNamespace(poller=fake_poller)))
    )

    with patch.object(orch.subprocess, "run", side_effect=fake_subprocess_run):
        asyncio.run(
            orch.drain_work_queue(
                client=client,
                environment_id="env1",
                environment_key="key1",
                image="img:dev",
                gcp_key_path=None,
                drain=True,
            )
        )

    records = [json.loads(l) for l in log_path.read_text().splitlines()]
    events_by_work = {}
    for r in records:
        events_by_work.setdefault(r["work_id"], []).append(r["event"])

    # w1 was in flight when SIGTERM arrived: it must still have a matching
    # start+exit pair, not a dangling start.
    assert events_by_work["w1"] == ["container_start", "container_exit"]
    # w2 must never have been dispatched - the loop stopped after w1.
    assert "w2" not in events_by_work

    orch._STOP_REQUESTED = False
