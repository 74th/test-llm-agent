"""Managed Agents のドライバ: セッションを作り、依頼を送り、idle までイベントを集めて、セッションを終了する。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import anthropic

from .config import ROOT, anthropic_api_key

STATE = ROOT / ".provisioned.json"


def load_state() -> dict[str, Any]:
    if not STATE.exists():
        raise RuntimeError(".provisioned.json がありません。scripts/provision.py を実行してください")
    return json.loads(STATE.read_text())


def new_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=anthropic_api_key())


@dataclass
class ManagedRun:
    session_id: str
    prompt: str
    events: list[dict[str, Any]] = field(default_factory=list)  # 受け取ったイベント(必要な項目だけ)
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    elapsed_s: float = 0.0
    usage: dict[str, Any] | None = None

    @property
    def final_text(self) -> str:
        return "\n".join(self.texts)

    def tool_output(self) -> str:
        return "\n".join(r["content"] for r in self.tool_results)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "final_text": self.final_text}


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    for c in content:
        d = c if isinstance(c, dict) else c.model_dump()
        out.append(d.get("text") or json.dumps(d, ensure_ascii=False, default=str))
    return "\n".join(out)


def _is_terminal(event: Any) -> bool:
    if event.type == "session.status_terminated":
        return True
    if event.type != "session.status_idle":
        return False
    return getattr(getattr(event, "stop_reason", None), "type", None) != "requires_action"


def _handle(client: anthropic.Anthropic, run: ManagedRun, event: Any) -> None:
    d = event.model_dump(mode="json", exclude_none=True)
    run.events.append({k: d[k] for k in ("id", "type", "name", "input", "tool_use_id", "is_error", "stop_reason") if k in d})
    if event.type == "agent.message":
        run.texts.append(_content_text(event.content))
    elif event.type in ("agent.tool_use", "agent.mcp_tool_use", "agent.custom_tool_use"):
        run.tool_uses.append({"id": event.id, "type": event.type, "name": d.get("name"), "input": d.get("input")})
        if getattr(event, "evaluated_permission", None) == "ask":
            client.beta.sessions.events.send(
                session_id=run.session_id,
                events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "allow"}],
            )
    elif event.type in ("agent.tool_result", "agent.mcp_tool_result", "user.tool_result"):
        run.tool_results.append({
            "tool_use_id": d.get("tool_use_id"),
            "is_error": d.get("is_error"),
            "content": _content_text(d.get("content")),
        })
    elif event.type == "session.status_idle":
        run.stop_reason = (d.get("stop_reason") or {}).get("type")


def send_and_collect(client: anthropic.Anthropic, run: ManagedRun, prompt: str, on_event=None) -> None:
    seen: set[str] = set()
    with client.beta.sessions.events.stream(session_id=run.session_id) as stream:
        client.beta.sessions.events.send(
            session_id=run.session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
        )
        for event in stream:
            if event.id and event.id in seen:
                continue
            if event.id:
                seen.add(event.id)
            if event.type == "user.message":
                continue
            if on_event:
                on_event(event)
            _handle(client, run, event)
            if _is_terminal(event):
                break


def run_session(prompt: str, *, title: str = "verify-skills-in-sandbox", on_event=None) -> ManagedRun:
    """新しいセッションで 1 つの依頼を実行し、終わったらセッションを archive する。"""
    client = new_client()
    state = load_state()
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": state["agent_id"]},
        environment_id=state["environment_id"],
        title=title,
    )
    run = ManagedRun(session.id, prompt)
    t0 = time.monotonic()
    try:
        send_and_collect(client, run, prompt, on_event)
    finally:
        run.elapsed_s = round(time.monotonic() - t0, 1)
        try:
            s = client.beta.sessions.retrieve(session_id=session.id)
            u = getattr(s, "usage", None)
            run.usage = u.model_dump(mode="json") if u is not None else None
        except anthropic.APIError:
            pass
        try:
            client.beta.sessions.archive(session_id=session.id)
        except anthropic.APIError:
            pass
    return run
