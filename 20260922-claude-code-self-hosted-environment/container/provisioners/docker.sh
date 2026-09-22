#!/usr/bin/env bash
# Verification-only spawn-runner backend (design.md D7). Reads the work-order
# JWT from stdin and only ever reads the provisioner-agnostic SPAWN_* inputs
# — never CLAUDE_RUNNER_* — so the internal contract stays the only thing a
# GKE-based backend (provisioners/gke.sh.example) would need to reimplement.
set -euo pipefail

: "${SPAWN_ORDER_ID:?SPAWN_ORDER_ID not set}"
: "${SPAWN_RUNNER_IMAGE:?SPAWN_RUNNER_IMAGE not set}"
: "${SPAWN_RUNNER_ARGS:?SPAWN_RUNNER_ARGS not set}"

container_name="ccr-${SPAWN_ORDER_ID}"

# Rule 1 (idempotent on the order ID): a redelivered request must start at
# most one container. If ours is already there, we're done.
if docker inspect --type container "$container_name" >/dev/null 2>&1; then
  echo "docker.sh: container $container_name already exists, treating as submitted" >&2
  exit 0
fi

work_order_jwt=$(cat)
if [ -z "$work_order_jwt" ]; then
  echo "docker.sh: empty work-order JWT on stdin" >&2
  exit 2
fi

env_file=$(umask 077 && mktemp)
trap 'rm -f "$env_file"' EXIT

{
  printf 'SELF_HOSTED_RUNNER_ENVIRONMENT_SECRET=%s\n' "$work_order_jwt"
  [ -n "${GITHUB_PAT:-}" ] && printf 'GITHUB_PAT=%s\n' "$GITHUB_PAT"
  [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && printf 'GOOGLE_APPLICATION_CREDENTIALS=%s\n' "$GOOGLE_APPLICATION_CREDENTIALS"
} > "$env_file"

mount_args=()
if [ -n "${SPAWN_RUNNER_MOUNTS:-}" ]; then
  for entry in $SPAWN_RUNNER_MOUNTS; do
    source_path="${entry%%:*}"
    rest="${entry#*:}"
    container_path="${rest%%:*}"
    mode="${rest#*:}"
    mount_args+=(-v "${source_path}:${container_path}:${mode}")
  done
fi

# shellcheck disable=SC2206  # SPAWN_RUNNER_ARGS is a plain space-separated
# flag list we control (see compose.ondemand.yaml), not attacker input.
spawn_args=($SPAWN_RUNNER_ARGS)

if ! docker run -d --rm \
      --name "$container_name" \
      --env-file "$env_file" \
      "${mount_args[@]}" \
      "$SPAWN_RUNNER_IMAGE" \
      "${spawn_args[@]}" >/dev/null; then
  echo "docker.sh: docker run failed for order $SPAWN_ORDER_ID" >&2
  exit 1
fi

echo "docker.sh: started $container_name" >&2
exit 0
