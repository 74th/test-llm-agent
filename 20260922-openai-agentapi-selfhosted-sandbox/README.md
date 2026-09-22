# OpenAI Agents API self-hosted session verifier

このリポジトリは、OpenAI Agents API の `self_hosted` セッションと、Docker 内で起動する `codex exec-server` の対応を検証するための小さな実験ハーネスです。セッション ID、環境 ID、executor コンテナ ID、ターン結果を分けて記録します。

## 事前条件

- Python 3.11 以上
- Docker Engine と Docker CLI
- 実 API を使う場合は、Agents API のセッション操作と Responses API 推論を許可したアプリ用キー
- 同じ organization、project、user または service account に属し、他の権限を無効にした executor 用環境キー
- executor 用イメージから `api.openai.com` と `codex-cloud-environments.chatgpt.com` へ outbound 接続できるネットワーク

アプリ用キーは `OPENAI_API_KEY` に設定し、ホストの Python CLI だけで使います。環境キーは `OPENAI_EXECUTOR_API_KEY` に設定し、実行時だけコンテナの `CODEX_API_KEY` に渡します。キーを Dockerfile、ソース、ログ、レポートへ書き込まないでください。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
# .env は手元で編集し、git に追加しない
set -a; . ./.env; set +a
```

## イメージの作成と確認

```bash
docker build --build-arg IMAGE_MARKER=self-hosted-verifier-image \
  -t "${OPENAI_EXECUTOR_IMAGE:-self-hosted-session-verifier:local}" .
docker run --rm "${OPENAI_EXECUTOR_IMAGE:-self-hosted-session-verifier:local}" \
  --help
docker run --rm --entrypoint sh "${OPENAI_EXECUTOR_IMAGE:-self-hosted-session-verifier:local}" \
  -c 'test "$(cat /etc/self-hosted-image-marker)" = self-hosted-verifier-image && command -v codex && codex exec-server --help'
```

イメージには `/workspace`、`/etc/self-hosted-image-marker`、Codex CLI が含まれます。executor の起動時に CLI が受け取る値は、セッション作成後に API が返す `environment.id` と `environment.remote_url` です。`remote_url` は再接続時も変更しません。

## CLI

```bash
self-hosted-verify --help
self-hosted-verify create
self-hosted-verify resume sess_... --input 'Read the marker and report the exact value.'
self-hosted-verify stop sess_...
```

`create` は `environment.type: self_hosted` と `/workspace` でセッションを作り、セッション ID、環境 ID、`remote_url` を `state/sessions.json` に保存して executor を起動します。`resume` は API からセッションを再取得して保存値と ID と URL を照合してから executor を起動します。同一セッションの同時要求はセッション単位のロックと Docker ラベルで一つの稼働中コンテナに収束します。

`OPENAI_AGENT_INSTRUCTIONS` は API の `agent.instructions` に、`OPENAI_CAPABILITY_DIRECTORIES` は API の `environment.capability_directories` に渡します。コンテナ内の `AGENTS.md`、skill、MCP の構成は [agent-configuration.md](docs/agent-configuration.md) を参照してください。

## AGENTS.md、skill、MCP の実 API 検証

executor イメージには `/workspace/AGENTS.md` と、確認用プラグイン
`/workspace/capabilities/plugins/config-probe` を含めています。次の設定で新規
self-hosted セッションを作ると、プラグインの skill と `.mcp.json` の MCP が公開されます。

```dotenv
OPENAI_CAPABILITY_DIRECTORIES=/workspace/capabilities/plugins/config-probe
OPENAI_AGENT_INSTRUCTIONS=Use the workspace instructions and relevant skills. Answer in Japanese.
```

`gpt-5.6-luna` で実行した比較結果は次の通りです。

| `capability_directories` | skill `configuration-probe` | MCP `openai_docs` |
| --- | --- | --- |
| プラグインルートを指定 | 利用できた。skill 指定の `SKILL_PROBE=amber-orbit` を返した | `search_openai_docs` の MCP call が `completed` |
| 省略 | 利用不可と回答 | 呼び出しなし |

どちらのセッションにも、harness が環境を確認するための組み込み `codex` MCP はあります。
比較対象では `openai_docs` は存在しなかったため、上段の skill と MCP は、既存の API
設定ではなく `capability_directories` で指定したコンテナ内プラグインによって公開されたと確認できます。
プラグインを追加・変更した場合は、新しいセッションを作って反映します。

## ローカル模擬検証

資格情報や API 課金なしで、全シナリオを実行できます。

```bash
self-hosted-verify verify --mock --output /tmp/self-hosted-mock-report.json
pytest -q
```

模擬検証の合否基準は次の通りです。

| シナリオ | 合格条件 |
| --- | --- |
| マーカー | 回答と対象ツール結果が同じコンテナのマーカーと一致する |
| 並行セッション | セッション ID、環境 ID、コンテナ ID がそれぞれ分離する |
| 接続失敗 | executor が起動状態にならない場合を `connection_failed` とする |
| ツール失敗 | ターン完了でも対象ツールが失敗すれば `tool_failed` とする |
| ストリーム切断 | 切断後に保存済み items から最終回答とツール結果を復元する |
| 対話継続 | コンテナを交換しても同一セッションの合言葉を復元する |
| 文脈分離 | 別セッションが合言葉を知らない |
| ファイル境界 | 永続マウントなしの新コンテナに前コンテナのファイルがない |

## ログと復元フック

`logs/container-lifecycle.jsonl` には次のイベントを一行 JSON として追記します。

- `start`: コンテナ起動要求とコンテナ ID
- `connect`: executor が稼働状態になったこと
- `start_failed`: 起動または接続待機の失敗
- `stop`: 終了コードを含む停止

各行には UTC の `timestamp`、`session_id`、`environment_id`、`container_id`、`result`、`exit_code` が入ります。`remote_url`、API キー、合言葉、ツール引数はログへ入れません。`state/`、`logs/`、`reports/` は `.gitignore` 対象です。

将来のワークスペース永続化を入れる位置は、executor コンテナを起動する直前の復元フックと、停止・削除する直前の保存フックです。今回の構成は永続ボリュームやスナップショットを作らないため、会話状態の継続とファイル状態の継続は独立して判定します。

## 実 API の実行

```bash
self-hosted-verify verify --output reports/real-api-report.json
```

実 API の結果は `reports/` に保存します。資格情報、モデル権限、Docker、ネットワークのいずれかが不足する場合、CLI は成功と表示せず `not_run_reason` を記録します。実測していない項目を模擬検証の結果で置き換えません。

## OpenAI 公式ドキュメントとの対応

- Self-hosted sandbox: <https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted>
- Run and continue sessions: <https://developers.openai.com/api/docs/guides/agents-api/sessions>
- Sandbox lifecycle: <https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle>
