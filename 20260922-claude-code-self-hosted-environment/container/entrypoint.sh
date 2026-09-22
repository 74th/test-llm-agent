#!/usr/bin/env bash
# Prepares the runner's host config from the mounted workspace, then execs
# into either `claude self-hosted-runner` or `claude self-hosted-runner
# orchestrator`, selected by $1. See design.md D1/D2/D8.
set -euo pipefail

mode="${1:-}"
if [ "$mode" != "runner" ] && [ "$mode" != "orchestrator" ]; then
  echo "entrypoint: first argument must be 'runner' or 'orchestrator' (got: '${mode}')" >&2
  exit 1
fi
shift

if [ -z "${GITHUB_PAT:-}" ]; then
  echo "entrypoint: GITHUB_PAT is not set" >&2
  exit 1
fi

# D2: read-only mount copied into the writable config root. Regenerated on
# every container start, so a workspace edit needs a restart to take effect
# (documented consequence of the runner's startup-only config snapshot).
rm -rf /opt/claude-config/.claude
mkdir -p /opt/claude-config
cp -r /mnt/workspace/.claude /opt/claude-config/.claude

# D8: GitHub MCP server, remote HTTP, token injected at runtime only — never
# baked into the image or into workspace/.
claude_json=$(jq -n --arg token "$GITHUB_PAT" '{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": ("Bearer " + $token) }
    }
  }
}')

# D1: the docs say .claude.json lives next to ~/.claude, not inside it, but
# the exact behavior when SELF_HOSTED_RUNNER_HOST_CONFIG_DIR-style layouts
# apply is worth confirming empirically, so write both locations (task 5.5
# records which one the runner actually read).
printf '%s\n' "$claude_json" > /opt/claude-config/.claude.json
printf '%s\n' "$claude_json" > /opt/claude-config/.claude/.claude.json

case "$mode" in
  runner)
    exec claude self-hosted-runner "$@"
    ;;
  orchestrator)
    exec claude self-hosted-runner orchestrator "$@"
    ;;
esac
