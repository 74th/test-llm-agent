#!/usr/bin/env bash
# Appends one JSON line to the shared event log. Usage:
#   log-event.sh <event> <session_id|-> [key=value ...]
# session_id "-" is stored as an empty string (pre-warming spawn requests
# have none). Never pass a secret value in a key=value pair (see D13 in
# design.md / task 7.2): this script only ever emits what its caller hands
# it, and callers are responsible for not handing it credentials.
set -euo pipefail

log_file="${CCR_EVENT_LOG:-/var/log/ccr-events/events.jsonl}"
mkdir -p "$(dirname "$log_file")"

event="${1:?usage: log-event.sh <event> <session_id|-> [key=value ...]}"
session_id="${2:-}"
[ "$session_id" = "-" ] && session_id=""
shift 2 || shift $#

ts=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)

json=$(jq -nc \
  --arg ts "$ts" \
  --arg event "$event" \
  --arg session_id "$session_id" \
  --args '
    ($ARGS.positional | map(split("=") | {(.[0]): (.[1:] | join("="))}) | add // {}) as $extra
    | {ts: $ts, event: $event, session_id: $session_id} + $extra
  ' "$@")

# Single write() call for atomicity under concurrent appenders (task 7.1):
# printf writes the whole line at once and the file is opened O_APPEND, so
# as long as the line stays under PIPE_BUF (4096 bytes on Linux) it can't
# interleave with another process's line.
printf '%s\n' "$json" >> "$log_file"
