from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    environment_id: str
    remote_url: str
    model: str
    workspace_directory: str = "/workspace"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionRecord":
        return cls(
            session_id=str(value["session_id"]),
            environment_id=str(value["environment_id"]),
            remote_url=str(value["remote_url"]),
            model=str(value["model"]),
            workspace_directory=str(value.get("workspace_directory", "/workspace")),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class ContainerRecord:
    container_id: str
    session_id: str
    environment_id: str
    marker: str
    started_at: str = field(default_factory=utc_now)
    running: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnResult:
    status: str
    final_answer: str = ""
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    stream_disconnected: bool = False
    error: str | None = None

    @property
    def turn_succeeded(self) -> bool:
        return self.status == "completed"

    @property
    def tool_succeeded(self) -> bool:
        return bool(self.tool_results) and all(
            result.get("status") == "completed" for result in self.tool_results
        )

    def outcome(self) -> str:
        if self.status == "connection_failed":
            return "connection_failed"
        if self.status in {"failed", "cancelled"}:
            return "turn_failed"
        if not self.turn_succeeded:
            return "turn_unknown"
        if self.tool_results and not self.tool_succeeded:
            return "tool_failed"
        return "success"


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    passed: bool
    observed: dict[str, Any]
    reason: str = ""


@dataclass
class VerificationReport:
    mode: str
    results: list[ScenarioResult] = field(default_factory=list)
    not_run_reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.not_run_reason is None and all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "passed": self.passed,
            "not_run_reason": self.not_run_reason,
            "results": [asdict(result) for result in self.results],
        }
