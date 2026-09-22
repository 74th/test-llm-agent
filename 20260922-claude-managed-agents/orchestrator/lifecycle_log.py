"""Append-only, flush-immediately JSON Lines lifecycle log for mode B.

One event per line so the file stays machine-readable line by line (a
crash mid-write never corrupts a previously-written line), and each
`log_event` call flushes + fsyncs so an event survives a hard kill of the
orchestrator process (container-lifecycle-log spec).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(os.environ.get("CMA_LIFECYCLE_LOG", "logs/container-lifecycle.jsonl"))

_lock = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log_event(event: str, path: Path | None = None, **fields: Any) -> None:
    """Append one lifecycle event as a single JSON line.

    `event` and `ts` are always set by this function; everything else
    (`session_id`, `work_id`, `environment_id`, `container_name`,
    `exit_code`, `duration_ms`, `error`, ...) is passed as keyword fields.
    """
    target = path or DEFAULT_LOG_PATH
    record = {"event": event, "ts": utc_now_iso(), **fields}
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)

    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
