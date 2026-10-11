#!/usr/bin/env bash
# sandboxd コンテナを起動する。sandboxd には認証が無いので、ポートはホストの loopback にだけ公開する。
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${SANDBOXD_IMAGE:-verify-sandboxd:dev}"
NAME="${SANDBOXD_CONTAINER:-verify-sandboxd}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" docker/sandboxd
fi
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:9090:9090 \
  "$IMAGE" --root-dir=/workspace >/dev/null

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/v1/health >/dev/null 2>&1; then
    echo "sandboxd started: $NAME"
    exit 0
  fi
  sleep 0.5
done
echo "sandboxd did not become healthy" >&2
docker logs "$NAME" >&2
exit 1
