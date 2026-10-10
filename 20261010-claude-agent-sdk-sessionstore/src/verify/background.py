"""バックグラウンド tool 検証用: ClaudeSDKClient のストリーミングで全メッセージを時刻つきで記録する。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    UserMessage,
)

from .config import MODEL, sdk_env

BG_SYSTEM_PROMPT = (
    "あなたは検証用アシスタントです。時間のかかるコマンドは Bash の run_in_background=true で実行し、"
    "完了を待たず、すぐに「開始しました」と返答します。バックグラウンドの完了通知を受け取ったら、"
    "出力に含まれる値を引用して報告します。sleep で待つ・ポーリングするのは禁止です。"
)


@dataclass
class Event:
    t: float
    kind: str
    detail: str
    origin: str | None = None


@dataclass
class Recorder:
    t0: float = field(default_factory=time.monotonic)
    events: list[Event] = field(default_factory=list)
    results: list[ResultMessage] = field(default_factory=list)

    def add(self, kind: str, detail: str, origin: str | None = None) -> None:
        self.events.append(Event(round(time.monotonic() - self.t0, 1), kind, detail[:200], origin))

    def record(self, m: Any) -> None:
        if isinstance(m, AssistantMessage):
            text = "".join(b.text for b in m.content if isinstance(b, TextBlock))
            tools = [getattr(b, "name", "") + str(getattr(b, "input", "")) for b in m.content if hasattr(b, "input")]
            self.add("assistant", text or " / ".join(tools))
        elif isinstance(m, ResultMessage):
            self.results.append(m)
            o = (m.origin or {}).get("kind") if m.origin else None
            self.add("result", m.result or "", o)
        elif isinstance(m, UserMessage):
            o = (m.origin or {}).get("kind") if m.origin else None
            c = m.content if isinstance(m.content, str) else str(m.content)
            self.add("user", c, o)
        elif isinstance(m, SystemMessage):
            self.add("system:" + m.subtype, str(m.data)[:150])

    def texts(self, kind: str = "assistant") -> list[Event]:
        return [e for e in self.events if e.kind == kind]


def bg_options(config_dir: Path, cwd: Path, **extra: Any) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODEL,
        env=sdk_env(config_dir),
        system_prompt=BG_SYSTEM_PROMPT,
        tools=["Bash"],
        allowed_tools=["Bash"],
        permission_mode="bypassPermissions",
        setting_sources=[],
        max_budget_usd=0.5,
        cwd=cwd,
        **extra,
    )


async def drain_until(client: ClaudeSDKClient, rec: Recorder, *, until, timeout: float) -> bool:
    """receive_messages を until(rec) が真になるまで読む。タイムアウトで False。"""

    async def _loop() -> None:
        async for m in client.receive_messages():
            rec.record(m)
            if until(rec):
                return

    try:
        await asyncio.wait_for(_loop(), timeout)
        return True
    except asyncio.TimeoutError:
        return False
