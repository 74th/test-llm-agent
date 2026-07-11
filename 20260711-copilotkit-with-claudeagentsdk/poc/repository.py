"""SQLite persistence for threads, messages, and run state."""
from __future__ import annotations
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

def _now() -> str:
    return datetime.now(UTC).isoformat()

class ThreadRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, agent_session_id TEXT,
                    state_json TEXT NOT NULL DEFAULT '{}', last_run_status TEXT NOT NULL DEFAULT 'idle',
                    active_run_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content_json TEXT NOT NULL, sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(thread_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS messages_thread_sequence ON messages(thread_id, sequence);
            """)
            db.execute("UPDATE threads SET last_run_status = 'interrupted', active_run_id = NULL WHERE last_run_status = 'running'")

    def create_thread(self, title: str = "新しいセッション") -> dict[str, Any]:
        thread_id, now = str(uuid.uuid4()), _now()
        with self.connect() as db:
            db.execute("INSERT INTO threads (id, title, state_json, last_run_status, created_at, updated_at) VALUES (?, ?, '{}', 'idle', ?, ?)", (thread_id, title.strip() or "新しいセッション", now, now))
        return self.get_thread(thread_id)

    def list_threads(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM threads ORDER BY updated_at DESC, created_at DESC").fetchall()
        return [self._thread(row, include_messages=False) for row in rows]

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
            if row is None:
                raise KeyError(thread_id)
            messages = db.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY sequence", (thread_id,)).fetchall()
        thread = self._thread(row, include_messages=True)
        thread["messages"] = [self._message(item) for item in messages]
        return thread

    def update_thread(self, thread_id: str, *, title: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if title is not None:
                cursor = db.execute("UPDATE threads SET title = ?, updated_at = ? WHERE id = ?", (title.strip() or "新しいセッション", _now(), thread_id))
                if cursor.rowcount == 0:
                    raise KeyError(thread_id)
        return self.get_thread(thread_id)

    def begin_run(self, thread_id: str, run_id: str) -> None:
        with self.connect() as db:
            cursor = db.execute("UPDATE threads SET last_run_status = 'running', active_run_id = ?, updated_at = ? WHERE id = ? AND active_run_id IS NULL", (run_id, _now(), thread_id))
            if cursor.rowcount == 0:
                if db.execute("SELECT 1 FROM threads WHERE id = ?", (thread_id,)).fetchone():
                    raise RuntimeError("thread already has an active run")
                raise KeyError(thread_id)

    def finish_run(self, thread_id: str, run_id: str, status: str, *, session_id: str | None = None, state: dict[str, Any] | None = None) -> None:
        if status not in {"completed", "error", "interrupted"}:
            raise ValueError(f"invalid final run status: {status}")
        with self.connect() as db:
            cursor = db.execute("UPDATE threads SET last_run_status = ?, active_run_id = NULL, agent_session_id = COALESCE(?, agent_session_id), state_json = COALESCE(?, state_json), updated_at = ? WHERE id = ? AND active_run_id = ?", (status, session_id, json.dumps(state, ensure_ascii=False) if state is not None else None, _now(), thread_id, run_id))
            if cursor.rowcount == 0:
                raise RuntimeError("run is no longer active")

    def add_message(self, thread_id: str, role: str, content: Any, *, message_id: str | None = None) -> dict[str, Any]:
        message_id, now = message_id or str(uuid.uuid4()), _now()
        with self.connect() as db:
            existing = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if existing:
                return self._message(existing)
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE thread_id = ?", (thread_id,)).fetchone()[0]
            db.execute("INSERT INTO messages (id, thread_id, role, content_json, sequence, created_at) VALUES (?, ?, ?, ?, ?, ?)", (message_id, thread_id, role, json.dumps(content, ensure_ascii=False), sequence, now))
            db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        return {"id": message_id, "threadId": thread_id, "role": role, "content": content, "sequence": sequence, "createdAt": now}

    @staticmethod
    def _thread(row: sqlite3.Row, *, include_messages: bool) -> dict[str, Any]:
        result = {"id": row["id"], "title": row["title"], "agentSessionId": row["agent_session_id"], "state": json.loads(row["state_json"]), "lastRunStatus": row["last_run_status"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}
        if include_messages:
            result["messages"] = []
        return result

    @staticmethod
    def _message(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "threadId": row["thread_id"], "role": row["role"], "content": json.loads(row["content_json"]), "sequence": row["sequence"], "createdAt": row["created_at"]}
