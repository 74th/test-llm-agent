#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${repo_root}"

mkdir -p tmp
date > tmp/stop-hook-time.txt

payload="$(cat || true)"
stop_hook_active=false

if printf '%s' "${payload}" | jq -e '.stop_hook_active // false' >/dev/null 2>&1; then
  stop_hook_active=true
fi

if ! command -v uv >/dev/null 2>&1; then
  if [[ "${stop_hook_active}" == "true" ]]; then
    cat <<'EOF'
{"continue":true,"systemMessage":"`uv` コマンドが見つからないため、終了時ユニットテストは実行できませんでした。"}
EOF
    exit 0
  fi

  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"Stop","decision":"block","reason":"セッション終了前にユニットテストを実行する設定ですが、`uv` コマンドが見つかりません。`uv` を使える状態にしてから完了してください。"}}
EOF
  exit 0
fi

if test_output="$(uv run python -m unittest discover -p '*_test.py' 2>&1)"; then
  cat <<'EOF'
{"continue":true,"systemMessage":"セッション終了時のユニットテストが成功しました。"}
EOF
  exit 0
fi

printf '%s\n' "${test_output}" >&2

if [[ "${stop_hook_active}" == "true" ]]; then
  cat <<'EOF'
{"continue":true,"systemMessage":"セッション終了時のユニットテストが失敗しました。無限ループ防止のため今回は停止を許可します。必要に応じて `uv run python -m unittest discover -p \"*_test.py\"` を手動で確認してください。"}
EOF
  exit 0
fi

cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"Stop","decision":"block","reason":"セッション終了前のユニットテストが失敗しました。`uv run python -m unittest discover -p \"*_test.py\"` を再実行して失敗を解消してください。"}}
EOF
