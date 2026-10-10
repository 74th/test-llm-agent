"""検証用のエージェント実行ヘルパー。"""

from __future__ import annotations

import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SessionStore,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from .config import MODEL, sdk_env

TOOL_NAME = "mcp__probe__issue_token"
SYSTEM_PROMPT = (
    "あなたは検証用アシスタントです。ユーザから依頼されたら issue_token ツールを呼びます。"
    "ツールの返した値は、ユーザが明示的に尋ねるまで返答に書いてはいけません。"
    "その場合の返答は「完了」の一言だけにします。"
)


@dataclass
class Turn:
    session_id: str | None = None
    text: str = ""
    messages: list[Any] = field(default_factory=list)
    result: ResultMessage | None = None


def make_probe_server(issued: list[str]):
    """ランダムなトークンを返す tool。発行値は issued に記録(正解値)。"""

    @tool("issue_token", "認証トークンを発行して返す", {})
    async def issue_token(args: dict[str, Any]) -> dict[str, Any]:
        token = "TK-" + secrets.token_hex(4).upper()
        issued.append(token)
        return {"content": [{"type": "text", "text": f"token={token}"}]}

    return create_sdk_mcp_server("probe", tools=[issue_token])


def new_config_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="claude-config-"))


async def run_turn(
    prompt: str,
    *,
    store: SessionStore | None = None,
    resume: str | None = None,
    issued: list[str] | None = None,
    config_dir: Path | None = None,
    cwd: Path | None = None,
    max_turns: int = 6,
    env_extra: dict[str, str] | None = None,
    **extra: Any,
) -> Turn:
    options = ClaudeAgentOptions(
        model=MODEL,
        env={**sdk_env(config_dir), **(env_extra or {})},
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"probe": make_probe_server(issued if issued is not None else [])},
        allowed_tools=[TOOL_NAME],
        tools=[],
        permission_mode="bypassPermissions",
        setting_sources=[],
        max_turns=max_turns,
        max_budget_usd=0.2,
        session_store=store,
        resume=resume,
        cwd=cwd,
        **extra,
    )
    turn = Turn()
    async for m in query(prompt=prompt, options=options):
        turn.messages.append(m)
        if isinstance(m, AssistantMessage):
            turn.text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        if isinstance(m, ResultMessage):
            turn.result = m
            turn.session_id = m.session_id
    return turn
