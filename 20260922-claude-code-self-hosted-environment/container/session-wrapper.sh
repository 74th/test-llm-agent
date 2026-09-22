#!/usr/bin/env bash
# --exec-path target (D9). Logs session start, then execs the runner's own
# pinned binary with auto mode forced on. A plain `exec` at the end keeps
# stdin and fd 3 attached (docs: "Keep stdin and file descriptor 3
# attached") — log-event.sh runs first and touches neither.
set -euo pipefail

/opt/claude/log-event.sh session_start "${CLAUDE_RUNNER_SESSION_ID:--}" \
  config_dir="${CLAUDE_CONFIG_DIR:-}" \
  client_platform="${CLAUDE_RUNNER_CLIENT_PLATFORM:-}" \
  account_email="${CCR_SESSION_ACCOUNT_EMAIL:-}"

exec "$CLAUDE_RUNNER_CLAUDE_BIN" "$@" --permission-mode auto
