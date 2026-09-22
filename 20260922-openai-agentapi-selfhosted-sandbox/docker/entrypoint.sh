#!/bin/sh
set -eu

marker="${SELF_HOSTED_CONTAINER_MARKER:-self-hosted-verifier-image}"
printf '%s\n' "$marker" > /workspace/.self-hosted-container-marker
exec codex exec-server "$@"
