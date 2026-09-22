from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .api import FakeSessionApi
from .config import Config
from .controller import SessionController, make_controller
from .docker import FakeDocker
from .docker import DockerError
from .models import ScenarioResult, VerificationReport
from .storage import LifecycleLogger


def build_fake_controller(root: Path, *, disconnect_once: bool = False) -> tuple[SessionController, FakeDocker, FakeSessionApi]:
    config = Config(
        openai_api_key="app-key-for-test",
        executor_api_key="executor-key-for-test",
        model="fake-model",
        image="fake-image",
        workspace_directory="/workspace",
        state_dir=root / "state",
        log_dir=root / "logs",
        report_dir=root / "reports",
    )
    config.ensure_directories()
    api = FakeSessionApi(disconnect_once=disconnect_once)
    docker = FakeDocker()
    logger = LifecycleLogger(config.log_dir / "container-lifecycle.jsonl", [config.openai_api_key, config.executor_api_key])
    return make_controller(config, api, docker, logger), docker, api


class VerificationRunner:
    def __init__(self, controller: SessionController, docker: Any, api: Any, model: str = "fake-model", mode: str = "mock"):
        self.controller = controller
        self.docker = docker
        self.api = api
        self.model = model
        self.mode = mode

    def run_all(self) -> VerificationReport:
        results = [
            self.marker_scenario(),
            self.parallel_sessions_scenario(),
            self.continuity_scenario(),
            self.failure_classification_scenario(),
            self.stream_recovery_scenario(),
        ]
        return VerificationReport(mode=self.mode, results=results)

    def marker_scenario(self) -> ScenarioResult:
        record = self.controller.create(self.model, "/workspace")
        container = self.controller.executors.ensure_running(record)
        marker_path = "/workspace/.self-hosted-container-marker"
        result = self.controller.send(record.session_id, f"Read {marker_path} and report the exact value.")
        expected = self.docker.exec(container.container_id, ["cat", marker_path]).strip()
        observed_marker = result.tool_results[0].get("output") if result.tool_results else None
        if isinstance(observed_marker, str):
            observed_marker = observed_marker.strip()
        passed = result.outcome() == "success" and expected in result.final_answer and observed_marker == expected
        self.controller.stop(record.session_id)
        return ScenarioResult(
            "marker_tool_match",
            passed,
            {"session_id": record.session_id, "environment_id": record.environment_id,
             "container_id": container.container_id, "expected_marker": expected,
             "observed_marker": observed_marker, "outcome": result.outcome()},
            "answer and tool output must contain the image marker" if not passed else "",
        )

    def parallel_sessions_scenario(self) -> ScenarioResult:
        def run_one(_: int) -> tuple[str, str, str]:
            record = self.controller.create(self.model, "/workspace")
            container = self.controller.executors.ensure_running(record)
            result = self.controller.send(record.session_id, "Read the container marker.")
            self.controller.stop(record.session_id)
            return record.session_id, record.environment_id, container.container_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(run_one, [1, 2]))
        passed = len({first[0], second[0], first[1], second[1], first[2], second[2]}) == 6
        return ScenarioResult("parallel_session_isolation", passed, {"first": first, "second": second})

    def continuity_scenario(self) -> ScenarioResult:
        record = self.controller.create(self.model, "/workspace")
        first_container = self.controller.executors.ensure_running(record)
        self.controller.send(record.session_id, "Remember secret: cobalt-otter.")
        file_path = "/workspace/created-only-in-first-container.txt"
        self.docker.exec(first_container.container_id, ["touch", file_path])
        self.controller.stop(record.session_id)
        resumed = self.controller.send(record.session_id, "What was the secret?")
        second_container = self.controller.executors.ensure_running(record)

        other = self.controller.create(self.model, "/workspace")
        isolated = self.controller.send(other.session_id, "What was the secret?")
        self.controller.stop(record.session_id)
        self.controller.stop(other.session_id)

        try:
            self.docker.exec(second_container.container_id, ["test", "-e", file_path])
        except Exception:
            file_persisted = False
        else:
            file_persisted = True
        conversation_continued = "cobalt-otter" in resumed.final_answer
        context_isolated = "cobalt-otter" not in isolated.final_answer
        passed = conversation_continued and context_isolated and not file_persisted
        return ScenarioResult(
            "session_continuity_and_file_boundary",
            passed,
            {"session_id": record.session_id, "environment_id": record.environment_id,
             "first_container_id": first_container.container_id, "second_container_id": second_container.container_id,
             "conversation_continued": conversation_continued, "other_session_isolated": context_isolated,
             "file_persisted_without_mount": file_persisted},
        )

    def failure_classification_scenario(self) -> ScenarioResult:
        record = self.controller.create(self.model, "/workspace")
        working_docker = self.controller.executors.docker
        self.controller.stop(record.session_id)
        self.controller.executors.docker = NeverStartsDocker()
        try:
            self.controller.executors.ensure_running(record, timeout_seconds=0.01)
        except DockerError:
            connection_failed = True
        else:
            connection_failed = False
        self.controller.executors.docker = working_docker
        tool_result = self.controller.send(
            record.session_id,
            "Run `cat /workspace/this-file-must-not-exist` with the shell tool. "
            "Do not create the file; report the command result.",
        )
        tool_failed = tool_result.outcome() == "tool_failed"
        self.controller.stop(record.session_id)
        return ScenarioResult(
            "connection_and_tool_failures_are_distinct",
            connection_failed and tool_failed,
            {"connection_failure_class": "connection_failed", "tool_failure_class": tool_result.outcome()},
        )

    def stream_recovery_scenario(self) -> ScenarioResult:
        root = Path(tempfile.mkdtemp(prefix="self-hosted-recovery-"))
        controller, docker, api = build_fake_controller(root, disconnect_once=True)
        record = controller.create(self.model, "/workspace")
        result = controller.send(record.session_id, "Read the container marker.")
        controller.stop(record.session_id)
        recovered = result.stream_disconnected and result.final_answer != "" and bool(result.items)
        return ScenarioResult("disconnected_stream_recovers_from_items", recovered, {"recovered": recovered})


def write_report(report: VerificationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class NeverStartsDocker(FakeDocker):
    """Docker double for the executor connection timeout path."""

    def inspect(self, container_id: str) -> dict[str, Any]:
        return {"State": {"Running": False, "ExitCode": 1}}
