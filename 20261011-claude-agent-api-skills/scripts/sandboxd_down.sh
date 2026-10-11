#!/usr/bin/env bash
set -euo pipefail
docker rm -f "${SANDBOXD_CONTAINER:-verify-sandboxd}" >/dev/null 2>&1 || true
echo "sandboxd stopped"
