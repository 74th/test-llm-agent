#!/usr/bin/env bash
# Mode A: one persistent worker container handling every session (design.md
# D4). Named volume on /workspace so state carries across sessions; the GCP
# key is read-only; ANTHROPIC_API_KEY is deliberately never set here (only
# ANTHROPIC_ENVIRONMENT_ID/KEY - see self-hosted-environment: 組織スコープの
# API キーはワーカーホストに置かない).
set -euo pipefail

IMAGE="${CMA_WORKER_IMAGE:-cma-verify-worker:dev}"
CONTAINER_NAME="${CMA_MODE_A_CONTAINER_NAME:-cma-mode-a-worker}"
VOLUME_NAME="${CMA_MODE_A_VOLUME:-cma-mode-a-workspace}"
GCP_KEY_PATH="${CMA_GCP_KEY_PATH:-$(pwd)/secrets/gcp-sa-key.json}"

: "${ANTHROPIC_ENVIRONMENT_ID:?Set ANTHROPIC_ENVIRONMENT_ID (from .provisioned.json) before starting mode A.}"
: "${ANTHROPIC_ENVIRONMENT_KEY:?Set ANTHROPIC_ENVIRONMENT_KEY (issued in the Console) before starting mode A.}"

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "warning: ANTHROPIC_API_KEY is set in this shell but will NOT be forwarded into the worker container (by design)." >&2
fi

docker volume create "$VOLUME_NAME" >/dev/null

docker run -d \
  --name "$CONTAINER_NAME" \
  -e ANTHROPIC_ENVIRONMENT_ID \
  -e ANTHROPIC_ENVIRONMENT_KEY \
  -v "$VOLUME_NAME:/workspace" \
  -v "$GCP_KEY_PATH:/run/secrets/gcp-sa-key.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa-key.json \
  "$IMAGE" run

echo "mode A worker started: $CONTAINER_NAME (image=$IMAGE, workspace volume=$VOLUME_NAME)"
echo "inspect with: docker inspect $CONTAINER_NAME"
echo "stop with:    docker stop $CONTAINER_NAME"
