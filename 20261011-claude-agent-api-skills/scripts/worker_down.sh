#!/usr/bin/env bash
set -euo pipefail
docker rm -f "${WORKER_CONTAINER:-verify-cma-worker}" >/dev/null 2>&1 || true
echo "worker stopped"
