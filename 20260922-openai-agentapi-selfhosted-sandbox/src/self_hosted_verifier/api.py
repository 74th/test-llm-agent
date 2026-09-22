from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .models import SessionRecord, TurnResult


class StreamDisconnected(RuntimeError):
    """Raised when an event stream ends before the turn result was observed."""


class SessionApi(Protocol):
    def create_session(
        self, model: str, workspace_directory: str, *, instructions: str | None = None,
        capability_directories: tuple[str, ...] = (),
    ) -> SessionRecord: ...

    def retrieve_session(self, session_id: str) -> SessionRecord: ...

    def send_input(self, session_id: str, text: str) -> TurnResult: ...

    def list_items(self, session_id: str) -> list[dict[str, Any]]: ...


def object_to_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: object_to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [object_to_dict(item) for item in value]
    if hasattr(value, "model_dump"):
        return object_to_dict(value.model_dump())
    if hasattr(value, "to_dict"):
        return object_to_dict(value.to_dict())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {key: object_to_dict(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def session_record_from_sdk(value: Any, model: str, workspace_directory: str) -> SessionRecord:
    environment = _field(value, "environment", {}) or {}
    return SessionRecord(
        session_id=str(_field(value, "id")),
        environment_id=str(_field(environment, "id")),
        remote_url=str(_field(environment, "remote_url")),
        model=model,
        workspace_directory=workspace_directory,
    )


class OpenAISessionApi:
    """Thin adapter around the beta Agents API used by the controller."""

    def __init__(self, api_key: str):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - packaging guard
            raise RuntimeError("Install the project dependencies before using the real API") from exc
        self.client = OpenAI(api_key=api_key)
        self._models: dict[str, tuple[str, str]] = {}

    def create_session(
        self, model: str, workspace_directory: str, *, instructions: str | None = None,
        capability_directories: tuple[str, ...] = (),
    ) -> SessionRecord:
        agent_instructions = instructions or (
            "You are a verification assistant. Use the executor to read the requested "
            "marker and report the exact tool result."
        )
        response = self.client.beta.agents.sessions.create(
            agent={
                "model": model,
                "instructions": agent_instructions,
            },
            environment={
                "type": "self_hosted",
                "workspace_directory": workspace_directory,
                "capability_directories": list(capability_directories),
            },
        )
        record = session_record_from_sdk(response, model, workspace_directory)
        self._models[record.session_id] = (model, workspace_directory)
        return record

    def retrieve_session(self, session_id: str) -> SessionRecord:
        response = self.client.beta.agents.sessions.retrieve(session_id)
        model, workspace = self._models.get(session_id, ("unknown", "/workspace"))
        return session_record_from_sdk(response, model, workspace)

    def send_input(self, session_id: str, text: str) -> TurnResult:
        events_seen: list[dict[str, Any]] = []
        try:
            with self.client.beta.agents.sessions.events.stream(session_id) as events:
                self.client.beta.agents.sessions.events.create(
                    session_id,
                    events=[
                        {
                            "type": "agent.session.input.message",
                            "input": [
                                {
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": text}],
                                }
                            ],
                        }
                    ],
                    timeout=60.0,
                )
                for event in events:
                    event_dict = object_to_dict(event)
                    events_seen.append(event_dict)
                    event_type = str(_field(event_dict, "type", ""))
                    if event_type in {"agent.session.environment.failed", "agent.session.failed"}:
                        return TurnResult(
                            status="connection_failed",
                            events=events_seen,
                            error=event_type,
                        )
                    if event_type == "agent.session.turn.failed":
                        return TurnResult(status="failed", events=events_seen, error=event_type)
                    if event_type == "agent.session.turn.cancelled":
                        return TurnResult(status="cancelled", events=events_seen, error=event_type)
                    if event_type == "agent.session.turn.completed":
                        break
                else:
                    raise StreamDisconnected("event stream closed before turn completion")
        except StreamDisconnected as exc:
            items = self.list_items(session_id)
            return TurnResult(
                status="unknown",
                events=events_seen,
                items=items,
                stream_disconnected=True,
                error=str(exc),
                final_answer=extract_final_answer(items),
                tool_results=extract_tool_results(items),
            )
        except Exception as exc:
            # Network and SDK stream errors are connection failures until the
            # authoritative saved items prove that the turn completed.
            items = self.list_items(session_id)
            return TurnResult(
                status="connection_failed" if not items else "unknown",
                events=events_seen,
                items=items,
                stream_disconnected=not items,
                error=f"{type(exc).__name__}: {exc}",
                final_answer=extract_final_answer(items),
                tool_results=extract_tool_results(items),
            )
        # The API stores the authoritative outcome and items. Retrieve those
        # items even after a complete stream so tool status is checked too.
        items = self.list_items(session_id)
        final_answer = extract_final_answer(items)
        tool_results = extract_tool_results(items)
        return TurnResult(status="completed", final_answer=final_answer, tool_results=tool_results,
                          events=events_seen, items=items)

    def list_items(self, session_id: str) -> list[dict[str, Any]]:
        page = self.client.beta.agents.sessions.items.list(session_id, order="asc", limit=100)
        raw = _field(page, "data", []) or []
        return [object_to_dict(item) for item in raw]


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def extract_tool_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items:
        for node in _walk(item):
            node_type = str(node.get("type", ""))
            if "tool" in node_type or node_type in {
                "command_execution", "computer_call_output", "shell_call_output"
            }:
                exit_code = node.get("exit_code")
                status = "failed" if exit_code not in (None, 0) else (
                    node.get("status") or node.get("output_status") or "completed"
                )
                results.append({"type": node_type, "status": str(status), "output": node.get("output")})
    return results


def extract_final_answer(items: list[dict[str, Any]]) -> str:
    candidates: list[str] = []
    for item in items:
        for node in _walk(item):
            node_type = str(node.get("type", ""))
            if node_type in {"message", "agent_message", "output_text"}:
                text = node.get("text")
                if isinstance(text, str) and text:
                    candidates.append(text)
    return candidates[-1] if candidates else ""


@dataclass
class FakeSession:
    record: SessionRecord
    items: list[dict[str, Any]]
    conversation_secret: str | None = None


class FakeSessionApi:
    """Deterministic API double used for all local scenario tests."""

    def __init__(self, *, disconnect_once: bool = False):
        self.sessions: dict[str, FakeSession] = {}
        self.disconnect_once = disconnect_once
        self._disconnect_used = False
        self._counter = 0

    def create_session(
        self, model: str, workspace_directory: str, *, instructions: str | None = None,
        capability_directories: tuple[str, ...] = (),
    ) -> SessionRecord:
        self._counter += 1
        session_number = self._counter
        record = SessionRecord(
            session_id=f"sess_fake_{session_number}",
            environment_id=f"env_fake_{session_number}",
            remote_url="https://api.openai.com/v1/agents/api",
            model=model,
            workspace_directory=workspace_directory,
        )
        self.sessions[record.session_id] = FakeSession(record, [])
        return record

    def retrieve_session(self, session_id: str) -> SessionRecord:
        return self.sessions[session_id].record

    def send_input(self, session_id: str, text: str) -> TurnResult:
        session = self.sessions[session_id]
        if "remember secret:" in text.lower():
            session.conversation_secret = text.split(":", 1)[1].strip()
        answer = ""
        tool_status = "completed"
        marker = ""
        if "marker" in text.lower():
            marker = "MARKER-" + session.record.environment_id
            answer = f"The executor marker is {marker}."
        elif "what was the secret" in text.lower() or "合言葉" in text:
            answer = session.conversation_secret or "I do not know that value."
        elif "fail tool" in text.lower() or "this-file-must-not-exist" in text:
            tool_status = "failed"
            answer = "The requested tool failed."
        else:
            answer = "Acknowledged."
        tool_item = {
            "type": "shell_tool_call",
            "status": tool_status,
            "output": marker or "ok",
        }
        message_item = {"type": "message", "text": answer}
        session.items.extend([tool_item, message_item])
        events = [
            {"type": "agent.session.environment.connected"},
            {"type": "agent.session.tool.completed" if tool_status == "completed" else "agent.session.tool.failed"},
            {"type": "agent.session.turn.completed"},
        ]
        if self.disconnect_once and not self._disconnect_used:
            self._disconnect_used = True
            return TurnResult(
                status="unknown",
                final_answer="",
                tool_results=[],
                events=events[:1],
                stream_disconnected=True,
                error="event stream disconnected",
            )
        return TurnResult(
            status="completed",
            final_answer=answer,
            tool_results=[tool_item],
            events=events,
            items=list(session.items),
        )

    def list_items(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.sessions[session_id].items)
