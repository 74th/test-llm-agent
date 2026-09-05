from types import SimpleNamespace

from poc import session_titles


def test_prefers_claude_custom_title(monkeypatch):
    monkeypatch.setattr(
        session_titles,
        "get_session_info",
        lambda _: SimpleNamespace(custom_title="Claudeのタイトル", summary="要約"),
    )
    assert session_titles.resolve_session_title("session", "最初の質問") == "Claudeのタイトル"


def test_falls_back_to_shortened_first_prompt(monkeypatch):
    monkeypatch.setattr(session_titles, "get_session_info", lambda _: None)
    prompt = "  とても長い   最初の質問です。" * 5
    title = session_titles.resolve_session_title("session", prompt)
    assert len(title) == 40
    assert title.endswith("…")
