from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .models import ContainerRecord, SessionRecord
from .storage import LifecycleLogger


class DockerError(RuntimeError):
    pass


class DockerClient(Protocol):
    def list(self, labels: dict[str, str]) -> list[dict[str, Any]]: ...
    def run(self, image: str, labels: dict[str, str], env: dict[str, str], command: list[str]) -> str: ...
    def inspect(self, container_id: str) -> dict[str, Any]: ...
    def stop(self, container_id: str) -> int: ...
    def remove(self, container_id: str) -> None: ...
    def exec(self, container_id: str, command: list[str]) -> str: ...


class SubprocessDocker:
    def _run(self, args: list[str]) -> str:
        completed = subprocess.run(["docker", *args], check=False, text=True, capture_output=True)
        if completed.returncode:
            raise DockerError(completed.stderr.strip() or "docker command failed")
        return completed.stdout.strip()

    def list(self, labels: dict[str, str]) -> list[dict[str, Any]]:
        args = ["ps", "-a", "--format", "{{json .}}"]
        for key, value in labels.items():
            args.extend(["--filter", f"label={key}={value}"])
        output = self._run(args)
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    def run(self, image: str, labels: dict[str, str], env: dict[str, str], command: list[str]) -> str:
        args = ["run", "-d"]
        for key, value in labels.items():
            args.extend(["--label", f"{key}={value}"])
        for key, value in env.items():
            args.extend(["--env", f"{key}={value}"])
        args.extend([image, *command])
        return self._run(args)

    def inspect(self, container_id: str) -> dict[str, Any]:
        return json.loads(self._run(["inspect", container_id]))[0]

    def stop(self, container_id: str) -> int:
        self._run(["stop", "--time", "10", container_id])
        inspected = self.inspect(container_id)
        return int(inspected.get("State", {}).get("ExitCode", 0))

    def remove(self, container_id: str) -> None:
        self._run(["rm", container_id])

    def exec(self, container_id: str, command: list[str]) -> str:
        return self._run(["exec", container_id, *command])


class ExecutorManager:
    LABEL_PREFIX = "self-hosted-verifier"

    def __init__(self, docker: DockerClient, logger: LifecycleLogger, image: str, executor_key: str):
        self.docker = docker
        self.logger = logger
        self.image = image
        self.executor_key = executor_key
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, threading.Lock())

    def ensure_running(self, record: SessionRecord, timeout_seconds: float = 30) -> ContainerRecord:
        with self._lock_for(record.session_id):
            labels = self._labels(record)
            existing = self.docker.list(labels)
            running = [item for item in existing if item.get("State") in {"running", "Up"}]
            if running:
                selected = running[0]
                for duplicate in running[1:]:
                    self._stop_and_remove(record, str(duplicate.get("ID")), "duplicate_removed")
                container_id = str(selected.get("ID"))
                container = self._record(record, container_id)
                self.logger.event("connect", session_id=record.session_id, environment_id=record.environment_id,
                                  container_id=container_id, result="existing")
                return container

            for stale in existing:
                self._stop_and_remove(record, str(stale.get("ID")), "stale_removed")
            try:
                container_id = self.docker.run(
                    self.image,
                    labels,
                    {
                        "CODEX_API_KEY": self.executor_key,
                        "SELF_HOSTED_CONTAINER_MARKER": f"MARKER-{record.environment_id}",
                    },
                    ["--remote", record.remote_url, "--environment-id", record.environment_id],
                )
                self.logger.event("start", session_id=record.session_id, environment_id=record.environment_id,
                                  container_id=container_id, result="started")
                deadline = time.monotonic() + timeout_seconds
                running_since: float | None = None
                while time.monotonic() < deadline:
                    inspected = self.docker.inspect(container_id)
                    if inspected.get("State", {}).get("Running") is True or inspected.get("State") == "running":
                        if running_since is None:
                            running_since = time.monotonic()
                        elif time.monotonic() - running_since >= 1:
                            self.logger.event("connect", session_id=record.session_id, environment_id=record.environment_id,
                                              container_id=container_id, result="running")
                            return self._record(record, container_id)
                    elif running_since is not None:
                        exit_code = inspected.get("State", {}).get("ExitCode")
                        raise DockerError(f"executor exited during startup (exit code {exit_code})")
                    time.sleep(0.05)
                raise DockerError("executor container did not become running before timeout")
            except Exception as exc:
                self.logger.event("start_failed", session_id=record.session_id, environment_id=record.environment_id,
                                  container_id=locals().get("container_id"), result=str(exc))
                if "container_id" in locals():
                    try:
                        inspected = self.docker.inspect(container_id)
                        state = inspected.get("State", {})
                        exit_code = state.get("ExitCode")
                        if not state.get("Running"):
                            self.docker.remove(container_id)
                            self.logger.event("stop", session_id=record.session_id, environment_id=record.environment_id,
                                              container_id=container_id, result="startup_failed_cleanup", exit_code=exit_code)
                    except Exception:
                        pass
                raise

    def stop(self, record: SessionRecord) -> None:
        with self._lock_for(record.session_id):
            for item in self.docker.list(self._labels(record)):
                self._stop_and_remove(record, str(item.get("ID")), "stopped")

    def recover_owned(self, records: list[SessionRecord]) -> list[str]:
        recovered: list[str] = []
        for record in records:
            for item in self.docker.list(self._labels(record)):
                if item.get("State") in {"running", "Up"}:
                    recovered.append(str(item.get("ID")))
        return recovered

    def _stop_and_remove(self, record: SessionRecord, container_id: str, result: str) -> None:
        if not container_id or container_id == "None":
            return
        self.logger.event("disconnect", session_id=record.session_id, environment_id=record.environment_id,
                          container_id=container_id, result="stopping")
        exit_code = self.docker.stop(container_id)
        self.logger.event("stop", session_id=record.session_id, environment_id=record.environment_id,
                          container_id=container_id, result=result, exit_code=exit_code)
        self.docker.remove(container_id)

    def _labels(self, record: SessionRecord) -> dict[str, str]:
        return {
            "com.openai.self-hosted-verifier": "true",
            "com.openai.session-id": record.session_id,
            "com.openai.environment-id": record.environment_id,
        }

    def _record(self, record: SessionRecord, container_id: str) -> ContainerRecord:
        marker = f"MARKER-{record.environment_id}"
        return ContainerRecord(container_id, record.session_id, record.environment_id, marker)


@dataclass
class FakeDockerContainer:
    container_id: str
    labels: dict[str, str]
    env: dict[str, str]
    command: list[str]
    marker: str
    running: bool = True
    workspace_files: set[str] | None = None
    removed: bool = False


class FakeDocker:
    """Docker double that models one fresh /workspace per container."""

    def __init__(self):
        self.containers: dict[str, FakeDockerContainer] = {}
        self._counter = 0

    def list(self, labels: dict[str, str]) -> list[dict[str, Any]]:
        return [
            {"ID": item.container_id, "State": "running" if item.running else "exited"}
            for item in self.containers.values()
            if not item.removed
            if all(item.labels.get(key) == value for key, value in labels.items())
        ]

    def run(self, image: str, labels: dict[str, str], env: dict[str, str], command: list[str]) -> str:
        self._counter += 1
        container_id = f"container_fake_{self._counter}"
        environment_id = labels["com.openai.environment-id"]
        self.containers[container_id] = FakeDockerContainer(
            container_id, labels, env, command, f"MARKER-{environment_id}", True, set()
        )
        return container_id

    def inspect(self, container_id: str) -> dict[str, Any]:
        item = self.containers[container_id]
        return {"State": {"Running": item.running, "ExitCode": 0 if item.running else 0}}

    def stop(self, container_id: str) -> int:
        self.containers[container_id].running = False
        return 0

    def remove(self, container_id: str) -> None:
        # Keep a history entry so the mock can verify that a fresh container
        # does not inherit the previous container's /workspace files.
        if container_id in self.containers:
            self.containers[container_id].removed = True

    def exec(self, container_id: str, command: list[str]) -> str:
        item = self.containers[container_id]
        if command == ["cat", "/workspace/.self-hosted-container-marker"]:
            return item.marker
        if command and command[0] == "touch" and len(command) == 2:
            if item.workspace_files is not None:
                item.workspace_files.add(command[1])
            return ""
        if command[:2] == ["test", "-e"] and len(command) == 3:
            if item.workspace_files and command[2] in item.workspace_files:
                return ""
            raise DockerError("file does not exist")
        raise DockerError(f"unsupported fake docker exec command: {command}")
