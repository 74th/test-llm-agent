"""Resolve display titles from Claude Agent SDK session metadata."""

from __future__ import annotations

from claude_agent_sdk import get_session_info


def resolve_session_title(session_id: str, first_prompt: str) -> str:
    """Prefer Claude's generated title, falling back to the first prompt."""
    try:
        info = get_session_info(session_id)
    except (OSError, ValueError):
        # Title lookup is best-effort and must never fail an otherwise valid run.
        info = None
    if info is not None:
        title = info.custom_title or info.summary
        if title and title.strip():
            return _shorten(title)
    return _shorten(first_prompt)


def _shorten(value: str, limit: int = 40) -> str:
    title = " ".join(value.split()).strip()
    if not title:
        return "新しいセッション"
    return title if len(title) <= limit else f"{title[:limit - 1]}…"
