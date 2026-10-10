"""JSONL ファイルに保存する検証用 SessionStore。

key ごとに 1 ファイル。append は uuid で重複排除する(SDK は再送で同じ entry を再配信しうる)。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

from claude_agent_sdk import (
    SessionKey,
    SessionListSubkeysKey,
    SessionStore,
    SessionStoreEntry,
    SessionStoreListEntry,
)


class FileSessionStore(SessionStore):
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._lock = asyncio.Lock()

    def _path(self, key: SessionKey) -> Path:
        base = self._root / key["project_key"]
        subpath = key.get("subpath")
        if subpath:
            return base / key["session_id"] / f"{subpath}.jsonl"
        return base / f"{key['session_id']}.jsonl"

    @staticmethod
    def _read(path: Path) -> list[SessionStoreEntry]:
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    async def append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        async with self._lock:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            seen = {e["uuid"] for e in self._read(path) if "uuid" in e} if path.exists() else set()
            with path.open("a", encoding="utf-8") as f:
                for entry in entries:
                    uuid = entry.get("uuid")
                    if uuid is not None:
                        if uuid in seen:
                            continue
                        seen.add(uuid)
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        path = self._path(key)
        if not path.exists():
            return None
        return self._read(path)

    async def list_sessions(self, project_key: str) -> list[SessionStoreListEntry]:
        base = self._root / project_key
        if not base.exists():
            return []
        return [
            {"session_id": p.stem, "mtime": int(p.stat().st_mtime * 1000)}
            for p in base.glob("*.jsonl")
        ]

    async def delete(self, key: SessionKey) -> None:
        if key.get("subpath") is None:
            self._path(key).unlink(missing_ok=True)
            shutil.rmtree(self._root / key["project_key"] / key["session_id"], ignore_errors=True)
        else:
            self._path(key).unlink(missing_ok=True)

    async def list_subkeys(self, key: SessionListSubkeysKey) -> list[str]:
        base = self._root / key["project_key"] / key["session_id"]
        if not base.exists():
            return []
        return [str(p.relative_to(base).with_suffix("")) for p in base.rglob("*.jsonl")]
