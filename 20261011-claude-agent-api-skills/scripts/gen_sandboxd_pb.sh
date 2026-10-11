#!/usr/bin/env bash
# sandboxd の Dockerfile と同じタグの process.proto から、ProcessService の Python スタブを生成する。
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${AGENT_SANDBOX_TAG:-v1.0.6}"
OUT=src/verify/sandboxd_pb
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/process/v1"
curl -fsSL "https://raw.githubusercontent.com/kubernetes-sigs/agent-sandbox/${TAG}/packages/sandboxd/spec/process/v1/process.proto" \
  -o "$WORK/process/v1/process.proto"

rm -rf "$OUT" && mkdir -p "$OUT"
uv run python -m grpc_tools.protoc -I "$WORK" --python_out="$OUT" --grpc_python_out="$OUT" "$WORK/process/v1/process.proto"
# 生成コードの `from process.v1 import ...` をパッケージ内の相対 import にする
sed -i 's/^from process\.v1 import/from . import/' "$OUT/process/v1/process_pb2_grpc.py"
touch "$OUT/__init__.py" "$OUT/process/__init__.py" "$OUT/process/v1/__init__.py"
echo "# generated from agent-sandbox ${TAG} packages/sandboxd/spec/process/v1/process.proto" > "$OUT/SOURCE"
echo "generated: $OUT (tag $TAG)"
