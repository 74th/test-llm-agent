#!/usr/bin/env bash
# Claude Code hook (session-internal, not a runner lifecycle hook — see
# design.md D13 "(2) セッション内"). Reads the hook's JSON payload from
# stdin and forwards it as one event to the shared JSONL log. Wired from
# settings.json for SessionStart / PostToolUse / Stop / SessionEnd.
set -euo pipefail

payload=$(cat)
session_id=$(printf '%s' "$payload" | jq -r '.session_id // "-"')
event_name=$(printf '%s' "$payload" | jq -r '.hook_event_name // "unknown"')
tool_name=$(printf '%s' "$payload" | jq -r '.tool_name // ""')

/opt/claude/log-event.sh "session_hook_${event_name}" "$session_id" \
  tool_name="$tool_name" account_email="${CCR_SESSION_ACCOUNT_EMAIL:-}"
