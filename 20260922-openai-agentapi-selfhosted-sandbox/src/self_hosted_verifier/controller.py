from __future__ import annotations

import threading
from typing import Any

from .api import SessionApi, extract_final_answer, extract_tool_results
from .docker import ExecutorManager
from .models import SessionRecord, TurnResult
from .storage import SessionStore


class SessionMismatch(RuntimeError):
    pass


class SessionController:
    """Coordinates API session state and the one-container-per-session rule."""

    def __init__(self, api: SessionApi, store: SessionStore, executors: ExecutorManager):
        self.api = api
        self.store = store
        self.executors = executors
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, threading.Lock())

    def create(
        self, model: str, workspace_directory: str, *, instructions: str | None = None,
        capability_directories: tuple[str, ...] = (),
    ) -> SessionRecord:
        record = self.api.create_session(
            model, workspace_directory, instructions=instructions,
            capability_directories=capability_directories,
        )
        self.store.save(record)
        self.executors.ensure_running(record)
        return record

    def resume(self, session_id: str) -> SessionRecord:
        saved = self.store.get(session_id)
        current = self.api.retrieve_session(session_id)
        if (current.environment_id, current.remote_url) != (saved.environment_id, saved.remote_url):
            raise SessionMismatch(
                "API session environment does not match local metadata; refusing to use a changed executor URL"
            )
        self.executors.ensure_running(saved)
        return saved

    def send(self, session_id: str, text: str) -> TurnResult:
        with self._lock_for(session_id):
            record = self.resume(session_id)
            result = self.api.send_input(session_id, text)
            if result.stream_disconnected:
                # Streams do not replay missed events. Recover from authoritative
                # session items after a disconnect.
                items = self.api.list_items(session_id)
                result.items = items
                result.final_answer = extract_final_answer(items)
                result.tool_results = extract_tool_results(items)
                result.status = "completed" if result.final_answer else "unknown"
                result.error = None if result.final_answer else result.error
            result.items = result.items or self.api.list_items(session_id)
            return result

    def stop(self, session_id: str) -> None:
        with self._lock_for(session_id):
            record = self.store.get(session_id)
            self.executors.stop(record)

    def recover_owned_containers(self) -> list[str]:
        return self.executors.recover_owned(self.store.all())


def make_controller(config: Any, api: SessionApi, docker: Any, logger: Any) -> SessionController:
    return SessionController(
        api=api,
        store=SessionStore(config.state_dir),
        executors=ExecutorManager(docker, logger, config.image, config.executor_api_key),
    )
