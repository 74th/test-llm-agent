#!/usr/bin/env bash
# self-hosted ワーカーを常駐コンテナとして 1 つ起動する(design D6)。
# コンテナに渡すのは ANTHROPIC_ENVIRONMENT_ID / ANTHROPIC_ENVIRONMENT_KEY だけ。API キーは渡さない。
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${WORKER_IMAGE:-verify-cma-worker:dev}"
NAME="${WORKER_CONTAINER:-verify-cma-worker}"

# .env から必要な 2 つだけを読む(ほかの値はこのシェルにも読み込まない)
get_env() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
ANTHROPIC_ENVIRONMENT_ID="${ANTHROPIC_ENVIRONMENT_ID:-$(get_env ANTHROPIC_ENVIRONMENT_ID)}"
ANTHROPIC_ENVIRONMENT_KEY="${ANTHROPIC_ENVIRONMENT_KEY:-$(get_env ANTHROPIC_ENVIRONMENT_KEY)}"
: "${ANTHROPIC_ENVIRONMENT_ID:?.env に ANTHROPIC_ENVIRONMENT_ID を書いてください}"
: "${ANTHROPIC_ENVIRONMENT_KEY:?Console で Environment key を発行し、.env に ANTHROPIC_ENVIRONMENT_KEY を書いてください}"
export ANTHROPIC_ENVIRONMENT_ID ANTHROPIC_ENVIRONMENT_KEY

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" -f docker/worker/Dockerfile .
fi
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -e ANTHROPIC_ENVIRONMENT_ID \
  -e ANTHROPIC_ENVIRONMENT_KEY \
  "$IMAGE" >/dev/null
echo "worker started: $NAME"
