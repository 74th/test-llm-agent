import asyncio
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import orchestrator.lifecycle_log as lifecycle_log
import orchestrator.main as orch


def make_work(work_id="w1", session_id="s1", environment_id="env1", secret="secret1", type_="session"):
    return SimpleNamespace(
        id=work_id,
        environment_id=environment_id,
        secret=secret,
        data=SimpleNamespace(id=session_id, type=type_),
    )


def test_container_name_is_deterministic_from_work_id():
    assert orch.container_name_for("w_abc123") == "cma-w_abc123"


def test_docker_run_command_forwards_secrets_valueless():
    cmd = orch.build_docker_run_command(
        "img:dev",
        container_name="cma-w1",
        forwarded_secret_env=["ANTHROPIC_WORK_SECRET", "ANTHROPIC_ENVIRONMENT_KEY"],
        gcp_key_path=None,
    )
    assert "ANTHROPIC_WORK_SECRET=" not in " ".join(cmd)
    assert cmd.count("-e") == 2
    assert "--rm" in cmd and "--name" in cmd and "cma-w1" in cmd
    assert cmd[-2:] == ["img:dev", "handle-item"]
    # /workspace must not be mounted in mode B
    assert "-v" not in cmd


def test_docker_run_command_mounts_gcp_key_readonly_without_leaking_path_as_secret():
    cmd = orch.build_docker_run_command(
        "img:dev",
        container_name="cma-w1",
        forwarded_secret_env=[],
        gcp_key_path="/host/secrets/gcp-sa-key.json",
    )
    assert "/host/secrets/gcp-sa-key.json:/run/secrets/gcp-sa-key.json:ro" in cmd
    assert "GOOGLE_APPLICATION_CREDENTIALS" in cmd
    assert "GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa-key.json" not in " ".join(cmd)


def test_run_one_work_item_logs_start_and_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle_log, "DEFAULT_LOG_PATH", tmp_path / "log.jsonl")

    with patch.object(
        orch.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ):
        orch.run_one_work_item("img:dev", make_work(), "env-key", None)

    lines = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [r["event"] for r in lines] == ["container_start", "container_exit"]
    assert lines[1]["exit_code"] == 0
    assert lines[1]["error"] is None
    assert lines[0]["container_name"] == lines[1]["container_name"] == "cma-w1"
    assert lines[0]["work_id"] == "w1"


def test_run_one_work_item_records_nonzero_exit_as_container_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle_log, "DEFAULT_LOG_PATH", tmp_path / "log.jsonl")

    with patch.object(
        orch.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    ):
        orch.run_one_work_item("img:dev", make_work(), "env-key", None)

    lines = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [r["event"] for r in lines] == ["container_start", "container_exit"]
    assert lines[1]["exit_code"] == 1
    assert "boom" in lines[1]["error"]


def test_run_one_work_item_records_start_failure_for_missing_image(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle_log, "DEFAULT_LOG_PATH", tmp_path / "log.jsonl")

    with patch.object(
        orch.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[], returncode=125, stdout="", stderr="Unable to find image 'nope:dev' locally"
        ),
    ):
        orch.run_one_work_item("nope:dev", make_work(), "env-key", None)

    lines = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [r["event"] for r in lines] == ["container_start", "container_start_failed"]
    assert "Unable to find image" in lines[1]["error"]


def test_run_one_work_item_never_logs_the_secret_value(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle_log, "DEFAULT_LOG_PATH", tmp_path / "log.jsonl")

    with patch.object(
        orch.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ):
        orch.run_one_work_item("img:dev", make_work(secret="TOP-SECRET-VALUE"), "env-key-value", None)

    raw = (tmp_path / "log.jsonl").read_text()
    assert "TOP-SECRET-VALUE" not in raw
    assert "env-key-value" not in raw


def test_drain_skips_non_session_items_without_running_docker(monkeypatch):
    calls = []
    monkeypatch.setattr(orch, "run_one_work_item", lambda *a, **k: calls.append(a))

    async def fake_poller(**kwargs):
        for w in [make_work(work_id="w-notsession", type_="deployment_run"), make_work(work_id="w-session")]:
            yield w

    client = SimpleNamespace(beta=SimpleNamespace(environments=SimpleNamespace(work=SimpleNamespace(poller=fake_poller))))

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

    assert len(calls) == 1
    assert calls[0][1].id == "w-session"
