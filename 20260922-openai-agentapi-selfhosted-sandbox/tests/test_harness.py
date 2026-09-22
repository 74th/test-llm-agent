from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from self_hosted_verifier.api import FakeSessionApi, extract_final_answer, extract_tool_results
from self_hosted_verifier.config import Config, ConfigurationError
from self_hosted_verifier.controller import SessionController, make_controller
from self_hosted_verifier.docker import ExecutorManager, FakeDocker
from self_hosted_verifier.models import SessionRecord
from self_hosted_verifier.scenarios import VerificationRunner, build_fake_controller
from self_hosted_verifier.storage import LifecycleLogger, SessionStore


def test_cli_help_is_available() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "self_hosted_verifier", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "verify" in completed.stdout


def test_configuration_requires_both_keys_and_model() -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        Config.from_env({})
    with pytest.raises(ConfigurationError, match="OPENAI_EXECUTOR_API_KEY"):
        Config.from_env({"OPENAI_API_KEY": "app", "OPENAI_MODEL": "model"})
    config = Config.from_env(
        {"OPENAI_API_KEY": "app", "OPENAI_EXECUTOR_API_KEY": "executor", "OPENAI_MODEL": "model"}
    )
    assert config.public_dict()["model"] == "model"
    assert config.capability_directories == ()
    assert "app" not in str(config.public_dict())
    assert "executor" not in str(config.public_dict())


def test_configuration_reads_agent_and_capability_settings() -> None:
    config = Config.from_env({
        "OPENAI_API_KEY": "app", "OPENAI_EXECUTOR_API_KEY": "executor", "OPENAI_MODEL": "model",
        "OPENAI_AGENT_INSTRUCTIONS": "Follow the repository policy.",
        "OPENAI_CAPABILITY_DIRECTORIES": "/workspace/plugins/first, /workspace/plugins/second",
    })
    assert config.agent_instructions == "Follow the repository policy."
    assert config.capability_directories == ("/workspace/plugins/first", "/workspace/plugins/second")
    with pytest.raises(ConfigurationError, match="absolute paths"):
        Config.from_env({
            "OPENAI_API_KEY": "app", "OPENAI_EXECUTOR_API_KEY": "executor", "OPENAI_MODEL": "model",
            "OPENAI_CAPABILITY_DIRECTORIES": "relative/plugin",
        })


def test_session_store_preserves_concurrent_creates(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "state")

    def save(number: int) -> None:
        store.save(SessionRecord(f"sess-{number}", f"env-{number}", "https://example.invalid", "model"))

    threads = [threading.Thread(target=save, args=(number,)) for number in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {record.session_id for record in store.all()} == {f"sess-{number}" for number in range(12)}


def test_lifecycle_log_has_ids_and_no_secret(tmp_path: Path) -> None:
    secret = "executor-secret-value"
    path = tmp_path / "logs" / "container-lifecycle.jsonl"
    logger = LifecycleLogger(path, [secret])
    logger.event("start", session_id="sess-1", environment_id="env-1", container_id="ctr-1", result="started")
    payload = json.loads(path.read_text())
    assert payload["session_id"] == "sess-1"
    assert payload["environment_id"] == "env-1"
    assert payload["container_id"] == "ctr-1"
    assert payload["timestamp"].endswith("Z")
    assert secret not in path.read_text()


def test_duplicate_executor_requests_converge(tmp_path: Path) -> None:
    docker = FakeDocker()
    logger = LifecycleLogger(tmp_path / "lifecycle.jsonl")
    manager = ExecutorManager(docker, logger, "image", "restricted-key")
    record = SessionRecord("sess-1", "env-1", "https://example.invalid", "model")
    first = manager.ensure_running(record)
    second = manager.ensure_running(record)
    assert first.container_id == second.container_id
    assert len([item for item in docker.containers.values() if not item.removed and item.running]) == 1


def test_api_create_retrieve_and_resume_metadata(tmp_path: Path) -> None:
    controller, docker, api = build_fake_controller(tmp_path)
    record = controller.create("fake-model", "/workspace")
    loaded = controller.resume(record.session_id)
    assert loaded == record
    assert api.retrieve_session(record.session_id) == record
    assert docker.list({"com.openai.session-id": record.session_id})


def test_all_mock_scenarios_pass(tmp_path: Path) -> None:
    controller, docker, api = build_fake_controller(tmp_path)
    report = VerificationRunner(controller, docker, api).run_all()
    assert report.passed
    assert {result.name for result in report.results} >= {
        "marker_tool_match",
        "parallel_session_isolation",
        "session_continuity_and_file_boundary",
        "connection_and_tool_failures_are_distinct",
        "disconnected_stream_recovers_from_items",
    }


def test_app_key_is_never_passed_to_executor(tmp_path: Path) -> None:
    config = Config(
        "application-secret", "executor-secret", "model", "image", "/workspace",
        tmp_path / "state", tmp_path / "logs", tmp_path / "reports",
    )
    config.ensure_directories()
    docker = FakeDocker()
    api = FakeSessionApi()
    logger = LifecycleLogger(config.log_dir / "lifecycle.jsonl", [config.openai_api_key, config.executor_api_key])
    controller = make_controller(config, api, docker, logger)
    record = controller.create("model", "/workspace")
    container = docker.containers[controller.executors.ensure_running(record).container_id]
    assert container.env["CODEX_API_KEY"] == "executor-secret"
    assert "SELF_HOSTED_CONTAINER_MARKER" in container.env
    assert config.openai_api_key not in container.env.values()
    assert config.executor_api_key not in (tmp_path / "logs" / "lifecycle.jsonl").read_text()


def test_command_execution_items_supply_tool_result_and_final_answer() -> None:
    items = [
        {"type": "command_execution", "status": "completed", "exit_code": 1, "output": "missing"},
        {"type": "message", "content": [{"type": "output_text", "text": "The file is absent."}]},
    ]
    assert extract_tool_results(items) == [
        {"type": "command_execution", "status": "failed", "output": "missing"}
    ]
    assert extract_final_answer(items) == "The file is absent."
