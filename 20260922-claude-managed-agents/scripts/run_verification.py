"""Verification driver (design.md D7).

Creates a session against the provisioned Agent/Environment, drives it
through a fixed sequence of scenario prompts, answers `agent.mcp_tool_use`
confirmations, and prints a human-readable pass/fail summary with the
evidence (response text, tool events) each verdict is based on.

Usage: `python -m scripts.run_verification` (reads IDs from
`.provisioned.json`, credentials from `ANTHROPIC_API_KEY`).
"""

from __future__ import annotations

import dataclasses
import sys
from typing import Any

import anthropic

from common.config import AnthropicConfig, load_provisioned

SCENARIOS: list[tuple[str, str]] = [
    (
        "marker",
        "Use the container-probe skill to report the container marker, hostname, and workdir.",
    ),
    (
        "skills_list",
        "What Skills do you currently have access to? List their names.",
    ),
    (
        "mcp_list",
        "What tools does the 'github' MCP server give you access to? List their names, do not call any of them yet.",
    ),
    (
        "mcp_call",
        "Use a github MCP tool to look up the authenticated user (whoami-equivalent), and report what it returns.",
    ),
    (
        "bigquery",
        "Write and run a short script to find the row count and the 3 most recent rows of "
        "the BigQuery table nnyn-dev.house_monitor.co2. The table requires a partition filter "
        "on the `timestamp` column; do not assume the data is recent, so use a partition filter "
        "wide enough to cover the table's entire history (e.g. from year 2000 onward) rather than "
        "a recent time window. Report the row count and the most recent rows.",
    ),
    (
        "workspace_io",
        "Write the text 'cma-verification' to /workspace/probe.txt, then read it back and report the contents.",
    ),
]


@dataclasses.dataclass
class ScenarioResult:
    name: str
    prompt: str
    transcript: list[str] = dataclasses.field(default_factory=list)
    tool_events: list[dict[str, Any]] = dataclasses.field(default_factory=list)


def _is_terminal_idle(event: Any) -> bool:
    return event.type == "session.status_idle" and event.stop_reason.type != "requires_action"


def run_scenario(client: anthropic.Anthropic, session_id: str, name: str, prompt: str) -> ScenarioResult:
    result = ScenarioResult(name=name, prompt=prompt)

    seen_event_ids: set[str] = set()
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
        )

        # Lossless reconnect pattern (design.md D7): fetch full history once
        # the stream is open and buffering, dedupe against it as the live
        # stream catches up, so a dropped connection can't lose an
        # unresolved tool_confirmation and deadlock the session.
        for event in client.beta.sessions.events.list(session_id=session_id):
            seen_event_ids.add(event.id)
            _handle_event(client, session_id, event, result)

        for event in stream:
            if event.id and event.id in seen_event_ids:
                if _is_terminal_idle(event) or event.type == "session.status_terminated":
                    break
                continue
            if event.id:
                seen_event_ids.add(event.id)
            _handle_event(client, session_id, event, result)
            if _is_terminal_idle(event) or event.type == "session.status_terminated":
                break

    return result


def _handle_event(client: anthropic.Anthropic, session_id: str, event: Any, result: ScenarioResult) -> None:
    if event.type == "agent.message":
        for block in event.content:
            if block.type == "text":
                result.transcript.append(block.text)
    elif event.type in ("agent.tool_use", "agent.mcp_tool_use"):
        result.tool_events.append(
            {"type": event.type, "id": event.id, "name": getattr(event, "name", None), "input": getattr(event, "input", None)}
        )
        if getattr(event, "evaluated_permission", None) == "ask":
            client.beta.sessions.events.send(
                session_id=session_id,
                events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "allow"}],
            )
    elif event.type in ("agent.tool_result", "agent.mcp_tool_result"):
        result.tool_events.append({"type": event.type, "id": event.id})


def print_report(results: list[ScenarioResult]) -> None:
    for r in results:
        print(f"\n=== {r.name} ===")
        print(f"prompt: {r.prompt}")
        print("--- response ---")
        print("".join(r.transcript) or "(no text response)")
        print(f"--- tool events ({len(r.tool_events)}) ---")
        for ev in r.tool_events:
            print(f"  {ev}")


def main() -> None:
    anthropic_config = AnthropicConfig.load()
    client = anthropic.Anthropic(api_key=anthropic_config.api_key)

    state = load_provisioned()
    for key in ("agent_id", "environment_id", "vault_id"):
        if key not in state:
            sys.exit(f"{key} が .provisioned.json にありません。先に scripts/provision.py を実行してください。")

    session = client.beta.sessions.create(
        agent={"type": "agent", "id": state["agent_id"], "version": state.get("agent_version")},
        environment_id=state["environment_id"],
        vault_ids=[state["vault_id"]],
    )
    print(f"session {session.id} created")
    print(f"trace: https://platform.claude.com/workspaces/default/sessions/{session.id}")

    results = [run_scenario(client, session.id, name, prompt) for name, prompt in SCENARIOS]
    print_report(results)


if __name__ == "__main__":
    main()
