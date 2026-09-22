from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.run_verification import ScenarioResult, _handle_event, _is_terminal_idle


def test_is_terminal_idle_true_for_end_turn():
    event = SimpleNamespace(type="session.status_idle", stop_reason=SimpleNamespace(type="end_turn"))
    assert _is_terminal_idle(event) is True


def test_is_terminal_idle_false_for_requires_action():
    event = SimpleNamespace(type="session.status_idle", stop_reason=SimpleNamespace(type="requires_action"))
    assert _is_terminal_idle(event) is False


def test_is_terminal_idle_false_for_non_idle_event():
    event = SimpleNamespace(type="agent.message")
    assert _is_terminal_idle(event) is False


def test_handle_event_collects_text():
    result = ScenarioResult(name="x", prompt="p")
    event = SimpleNamespace(
        type="agent.message",
        content=[SimpleNamespace(type="text", text="hello "), SimpleNamespace(type="text", text="world")],
    )
    _handle_event(MagicMock(), "sesn_1", event, result)
    assert "".join(result.transcript) == "hello world"


def test_handle_event_auto_confirms_ask_permission_mcp_tool_use():
    client = MagicMock()
    result = ScenarioResult(name="x", prompt="p")
    event = SimpleNamespace(
        type="agent.mcp_tool_use",
        id="sevt_abc",
        name="search_issues",
        input={"q": "foo"},
        evaluated_permission="ask",
    )
    _handle_event(client, "sesn_1", event, result)

    client.beta.sessions.events.send.assert_called_once()
    _, kwargs = client.beta.sessions.events.send.call_args
    assert kwargs["session_id"] == "sesn_1"
    sent_event = kwargs["events"][0]
    assert sent_event["type"] == "user.tool_confirmation"
    assert sent_event["tool_use_id"] == "sevt_abc"
    assert sent_event["result"] == "allow"
    assert len(result.tool_events) == 1


def test_handle_event_does_not_confirm_when_already_allowed():
    client = MagicMock()
    result = ScenarioResult(name="x", prompt="p")
    event = SimpleNamespace(
        type="agent.tool_use", id="sevt_1", name="bash", input={}, evaluated_permission="allow"
    )
    _handle_event(client, "sesn_1", event, result)
    client.beta.sessions.events.send.assert_not_called()


def test_print_report_includes_prompt_response_and_tool_evidence(capsys):
    from scripts.run_verification import print_report

    result = ScenarioResult(
        name="marker",
        prompt="probe the container",
        transcript=["CONTAINER_PROBE_MARKER: image=x\n"],
        tool_events=[{"type": "agent.tool_use", "id": "sevt_1", "name": "bash", "input": {}}],
    )
    print_report([result])
    out = capsys.readouterr().out
    assert "marker" in out
    assert "probe the container" in out
    assert "CONTAINER_PROBE_MARKER" in out
    assert "sevt_1" in out
