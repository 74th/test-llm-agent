from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from .models import SessionRecord, utc_now


SECRET_NAME_RE = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.I)


class SessionStore:
    """Private JSON metadata store for session IDs and executor connection data."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "sessions.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save(self, record: SessionRecord) -> None:
        with self._lock:
            data = self._read_all()
            data[record.session_id] = record.to_dict()
            self._atomic_write(data)

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            data = self._read_all()
            try:
                return SessionRecord.from_dict(data[session_id])
            except KeyError as exc:
                raise KeyError(f"No local metadata for session {session_id}") from exc

    def all(self) -> list[SessionRecord]:
        with self._lock:
            return [SessionRecord.from_dict(value) for value in self._read_all().values()]

    def _read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _atomic_write(self, value: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix="sessions.", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class LifecycleLogger:
    """Append-only JSONL logger that excludes URLs and secret values by design."""

    def __init__(self, path: Path, secret_values: Iterable[str] = ()):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._secret_values = tuple(value for value in secret_values if value)

    def event(
        self,
        event: str,
        *,
        session_id: str,
        environment_id: str,
        container_id: str | None = None,
        result: str,
        exit_code: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": utc_now(),
            "event": event,
            "session_id": session_id,
            "environment_id": environment_id,
            "container_id": container_id,
            "result": result,
            "exit_code": exit_code,
        }
        serialized = json.dumps(payload, sort_keys=True)
        for secret in self._secret_values:
            if secret in serialized:
                raise ValueError("Refusing to write a lifecycle event containing a secret")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
