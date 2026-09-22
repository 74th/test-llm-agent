# Claude Managed Agents — 自前コンテナ環境の検証ハーネス

Claude Managed Agents の self-hosted Environment（`config: {type: "self_hosted"}`）を使い、
Anthropic のクラウドサンドボックスではなく自前の Docker コンテナでエージェントのツール実行が
できることを確かめる検証ハーネス。あわせて、指定した skills / MCP がエージェントに認識される
こと、コンテナ内にしか存在しない資格情報（GCP サービスアカウントキー）で実作業ができること、
セッション単位でコンテナを起動・終了させる運用（将来のワークスペース永続化の土台）が成立する
ことを確認する。

## 構成

**責務の境界:**

| レイヤー | 実行場所 |
|---|---|
| エージェントループ（モデル推論、ツール呼び出しの決定） | Anthropic 側（Managed Agents） |
| ツール実行（bash / read / write / edit / glob / grep） | **自前コンテナ**（このリポジトリの `worker/`） |
| MCP ツール呼び出し（GitHub hosted MCP） | Anthropic 側（Anthropic の orchestration layer が MCP サーバに接続） |
| `web_search` / `web_fetch` | Anthropic 側（環境の種類によらず常に） |

つまり「自前コンテナで動く」のはファイル操作と bash だけで、MCP はコンテナを経由しない。この
検証で MCP と自前コンテナ実行を両方確かめるのはそのため（両方が別々に成立することを示す）。

**ディレクトリ構成:**

```
common/       設定読み込み（環境変数・.provisioned.json）
worker/       コンテナに入るワーカー本体（run / handle-item の2サブコマンド、1イメージ）
orchestrator/ モード B 用オーケストレータ（work poller + docker run + ライフサイクルログ）
scripts/      provision.py（Agent/Environment/skills/MCP/vault 登録）、run_verification.py（検証ドライバ）、mode_a_up.sh
skills/       検証用カスタムスキル（container-probe）
docker/       ワーカーイメージの Dockerfile
terraform/    BigQuery アクセス用サービスアカウントと IAM
mcp.json      検証対象の MCP サーバ宣言（GitHub hosted MCP）
logs/         モード B のライフサイクルログ出力先（gitignore 対象）
secrets/      GCP サービスアカウントキーなど（gitignore 対象）
```

**モード A（常駐単一コンテナ）と モード B（セッション毎コンテナ）:**

同じ Docker イメージ（`docker/Dockerfile`）を、エントリポイントの引数だけ変えて両方に使う。

| | モード A | モード B |
|---|---|---|
| 起動単位 | ワーカーコンテナ 1 つが起動しっぱなし | セッションの work item ごとに使い捨てコンテナ |
| エントリポイント | `worker run`（`EnvironmentWorker.run()`） | `worker handle-item`（`EnvironmentWorker.handle_item()`） |
| 起動コマンド | `bash scripts/mode_a_up.sh` | `python -m orchestrator.main`（ホスト側で常駐） |
| `/workspace` | named volume（状態を持ち越す） | マウントなし（状態を持ち越さない） |
| ライフサイクルログ | なし（コンテナ自体が常駐するため対象外） | `logs/container-lifecycle.jsonl` |

## 人間が事前に設定すべき内容

以下はすべてこのリポジトリの外で、人間が用意する。

1. **Anthropic API キー** — `scripts/provision.py` と `scripts/run_verification.py` が使う。
   `export ANTHROPIC_API_KEY=sk-ant-...`。**ワーカーホスト（モード A のコンテナ、モード B の
   オーケストレータ）には絶対に設定しない** — 組織スコープの資格情報をツール実行環境に晒さない
   ため（design.md のリスク参照）。
2. **Environment key** — `scripts/provision.py` で self-hosted Environment を作成した後、
   Anthropic Console の当該 Environment のページで発行する（`sk-ant-oat01-...`）。
   `export ANTHROPIC_ENVIRONMENT_ID=env_...` / `export ANTHROPIC_ENVIRONMENT_KEY=sk-ant-oat01-...`
   としてワーカーホスト側に設定する。
3. **GitHub PAT** — GitHub hosted MCP（`https://api.githubcopilot.com/mcp/`）の認証情報として
   vault に登録する。GitHub の Settings → Developer settings → Personal access tokens で発行し、
   `export GITHUB_PAT=ghp_...`。スコープは検証したい操作（例: `repo` read や `read:user`）に合わせ
   る。**もし GitHub 側が static bearer トークンでの MCP 認証を拒否する場合**（OAuth 必須の可能
   性がある。design.md のリスク参照）、MCP サーバのドキュメントに従って OAuth トークンを取得し、
   `provision.py` の `ensure_github_vault_credential` を `mcp_oauth` credential 形式に切り替える。
4. **GCP サービスアカウントキー** — `terraform/` を適用した後、`terraform/README.md` の手順で
   `gcloud iam service-accounts keys create secrets/gcp-sa-key.json` により発行する。
   `nnyn-dev` プロジェクトで Terraform を適用する権限（`roles/iam.serviceAccountAdmin` /
   `roles/bigquery.dataOwner` 相当）が必要。
5. **バージョン要件** — Docker、Terraform（`>= 1.5`、`hashicorp/google ~> 6.0`）、Python
   `>= 3.11`。ワーカーイメージは `python:3.12-slim` ベースで `/bin/bash` を含む（Anthropic SDK
   のワーカーヘルパーの必須要件）。
6. **秘密の置き場所** — `secrets/`、`.env`、`.provisioned.json`、`logs/`、
   `terraform/.terraform*`、`*.tfstate*` はすべて `.gitignore` 済み。これらをバージョン管理に
   入れない。`.provisioned.json` には ID のみが入り、トークンや秘密の値そのものは入らない。

## 検証手順

依存関係のインストール:

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
```

### 1. Terraform 適用（GCP サービスアカウント）

```bash
cd terraform && terraform init && terraform plan && terraform apply
gcloud iam service-accounts keys create ../secrets/gcp-sa-key.json \
  --iam-account "$(terraform output -raw service_account_email)"
cd ..
```

### 2. ワーカーイメージのビルド

```bash
docker build -f docker/Dockerfile --build-arg IMAGE_IDENTIFIER="$(git rev-parse --short HEAD 2>/dev/null || echo dev)" \
  -t cma-verify-worker:dev .
```

### 3. プロビジョニング（Environment / skill / MCP / vault / Agent）

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_PAT=ghp_...
.venv/bin/python -m scripts.provision
```

`.provisioned.json` に `environment_id` / `skill_id` / `vault_id` / `agent_id` などが書かれる。
Console で `environment_id` の Environment key を発行し、環境変数に設定する:

```bash
export ANTHROPIC_ENVIRONMENT_ID=$(python -c "import json;print(json.load(open('.provisioned.json'))['environment_id'])")
export ANTHROPIC_ENVIRONMENT_KEY=sk-ant-oat01-...
```

### 4. モード A の起動と検証

```bash
bash scripts/mode_a_up.sh
# ANTHROPIC_API_KEY はこのシェルに残したまま run_verification だけが使う
.venv/bin/python -m scripts.run_verification   # 1 回目
.venv/bin/python -m scripts.run_verification   # 2 回目（状態の持ち越しを見る）
docker stop cma-mode-a-worker
```

### 5. モード B の起動と検証

```bash
.venv/bin/python -m orchestrator.main --image cma-verify-worker:dev --gcp-key "$(pwd)/secrets/gcp-sa-key.json" &
.venv/bin/python -m scripts.run_verification
kill %1   # SIGTERM で正常終了することを確認する
```

### 検証項目と手順の対応

| # | 検証項目 | 対応する手順 |
|---|---|---|
| 1 | 自前コンテナでの実行 | 手順 4・5 の `run_verification` の "marker" シナリオ |
| 2 | skills の認識 | "marker"（スキル実行）・"skills_list"（スキル列挙）シナリオ |
| 3 | MCP の認識 | "mcp_list"（列挙）・"mcp_call"（実行）シナリオ |
| 4 | モード A（常駐・複数セッション） | 手順 4 を 2 回実行、`docker ps` でコンテナが起動したままであることを確認 |
| 5 | モード B のライフサイクルイベント | 手順 5 実行後、`logs/container-lifecycle.jsonl` を確認 |
| 6 | BigQuery アクセス | "bigquery" シナリオ |

## 人間が確認すべき内容

| 項目 | どこを見るか | 何が見えていれば合格か |
|---|---|---|
| 1. 自前コンテナでの実行 | `run_verification` の "marker" シナリオの出力 | `CONTAINER_PROBE_MARKER` の値が、`docker build` 時に `--build-arg IMAGE_IDENTIFIER` に渡した値と一致する（Anthropic のクラウドサンドボックスでは絶対に出ない値） |
| 2. skills の認識 | 同上、および "skills_list" シナリオ | container-probe スキル特有の固定 3 行フォーマットで応答している。スキル一覧に `container-probe` が出る |
| 3. MCP の認識 | "mcp_list" / "mcp_call" シナリオ、および Console のセッションビューア（`?event={event_id}` で該当イベントに飛べる） | GitHub MCP のツール名が具体的に列挙され、実際の呼び出し（`agent.mcp_tool_use` → `user.tool_confirmation` → `agent.mcp_tool_result`）が成立している |
| 4. モード A | `docker ps` の出力、2 回の `run_verification` 実行結果 | 同じコンテナ名 (`cma-mode-a-worker`) が両方の実行中ずっと起動したまま。1 セッション目で書いたファイルが 2 セッション目のシナリオで読める |
| 5. モード B のライフサイクルイベント | `logs/container-lifecycle.jsonl` | 1 行 1 JSON。`work_id` ごとに `container_start` と `container_exit`（または `container_start_failed`）が対になっている。1 セッション内のターン数と、そのセッションに対応する `work_id` の `container_start` 件数が一致する（実測値は design.md / このファイルの検証ログに記録） |
| 6. BigQuery アクセス | "bigquery" シナリオの出力 | 行数と直近データが具体的な値で返っている（`nnyn-dev.house_monitor.co2` は `timestamp` カラムでパーティション化されているため、クエリに `WHERE timestamp >= ...` のようなフィルタが必要）。マウントしたキー以外に BigQuery 認証情報がないことを踏まえ、コンテナ内資格情報での実行だと判断できる |

**ライフサイクルログの 1 レコード例:**

```json
{"event":"container_start","ts":"2026-09-22T03:10:00.123Z","session_id":"sesn_...","work_id":"witm_...","environment_id":"env_...","container_name":"cma-witm_..."}
{"event":"container_exit","ts":"2026-09-22T03:10:12.456Z","session_id":"sesn_...","work_id":"witm_...","environment_id":"env_...","container_name":"cma-witm_...","exit_code":0,"duration_ms":12333,"error":null}
```

## 通し検証の実測値・既知の制約（2026-09-22 実施）

ホスト側 Claude Code から実際の Managed Agents API を通しで実行して判明した内容（コスト抑制のため
`claude-haiku-4-5` を使用）。

- **コンテナ起動回数はターン単位ではなくセッション単位。** モード B は「work item = セッションの
  1 ラン」であり、1 セッション内で何ターン・何回ツールを呼んでもコンテナは 1 つのまま処理する。
  6 シナリオ（6 ターン）のセッションでも `container_start` / `container_exit` は 1 組だけ記録され、
  所要時間は約 99 秒だった。ターンごとにコンテナが立つわけではない点に注意。
- **GitHub hosted MCP は `static_bearer`（PAT）の認証で十分だった。** OAuth への切り替えは不要
  だった。
- **既知の制約: skills はコンテナへのダウンロードは成功するが、モデルが自発的に読みにいかない
  ことがある。** `provision.py` で Agent に添付した skill は `EnvironmentWorker` が正しく
  `/workspace/skills/<name>/SKILL.md` としてダウンロードすることを直接確認した（`ls` / `cat` で
  中身が読めた）。しかし「container-probe skill を使って」「利用可能な skill を列挙して」という
  自然な問いかけに対し、`claude-haiku-4-5` は `/workspace/skills/` を自発的に探索せず、
  `container-probe` をシェルコマンドとして実行しようとして失敗する、または「skill システムには
  アクセスがない」と回答する、という挙動を複数回のセッションで再現した。skill 配信の仕組み自体
  （アップロード → Agent への添付 → コンテナへのダウンロード）は機能しているので、これは
  self-hosted 環境（またはこのモデル階層）でモデルに「skills ディレクトリを見よ」と気づかせる
  仕組みが働いていない可能性を示す。より上位のモデル（`claude-opus-5` など）や、コンテナ内から
  明示的にパスを指示するプロンプトでは異なる結果になる可能性があり、追加調査が必要。
- **Agent の `skills` に明示的なバージョン ID を渡すと skill ダウンロードが失敗する不具合を
  発見・回避した。** `{"type": "custom", "skill_id": ..., "version": "skver_..."}` のように
  `client.skills.versions.create()` が返す具体的なバージョン ID を渡すと、セッション作成時に
  その情報が内部的な数値 ID（例: `1790051182361008`）に変換されてセッションのスナップショットに
  記録され、ワーカーが `client.beta.skills.versions.retrieve()` でそれを解決しようとして
  `400 Invalid version id` エラーになり、skill のダウンロードがサイレントに失敗する
  （エラーはワーカーのログにのみ出て、セッションのイベントには一切現れない）。回避策として
  `version` キーを省略する（`"latest"` を使う）ことでダウンロードが成功することを確認した。
  `scripts/provision.py` の `build_agent_config` は既にこの回避策を反映している。

## ワークスペース永続化に向けた下調べ（2026-09-22 実施）

この変更のスコープはライフサイクルイベントが取れることの確認までで、永続化の実装自体は
含まない（前節「制約・スコープ外」参照）。次の変更に向けて、フックの実装可能性と必要な
情報の取得経路だけ実測で確認した。

- **`container_exit` は「プロセスが死んで終わる」だけでなく、ホスト側から確実に介入できる。**
  `orchestrator/main.py` の `run_one_work_item` は `subprocess.run(cmd, ...)` を同期呼び出し
  しているため、`docker run` が返る＝コンテナが終了する瞬間、オーケストレータ自身の Python
  コードがそのまま実行を継続する。「外部プロセスの終了を検知する」のではなく「自分のコード
  内でその場に居合わせている」構造なので、`log_event("container_exit", ...)` を呼ぶ直前
  （ワークスペース保存フックの予定地としてコメントを置いてある箇所）に任意の後処理を挟める。
  同様に、コンテナ起動直前（ワークスペース復元フックの予定地）にも任意の前処理を挟める。
  ただし `docker run --rm` を使っているため、コンテナはexitと同時に実体ごと削除される
  （`docker ps -a` で実際に確認済み: モード B を実行後、`cma-*` という名前のコンテナは
  起動中・停止済みのどちらにも一切残らない）。そのため `docker cp` で後から取り出す方式は
  使えず、永続化を実装するなら `/workspace` をホストのディレクトリに bind mount しておく
  必要がある（現状は意図的に未マウント。D4 参照）。
- **コンテナ内側のシグナル配線（`worker/__main__.py` の SIGINT/SIGTERM ハンドラ）は、
  オーケストレータやユーザーが明示的にシグナルを送った場合にのみ効く。** セッションが
  idle になって `EnvironmentWorker.handle_item()` が自然に完了して終了する通常経路は
  Anthropic SDK 内部の処理であり、こちら側のコードから割り込む口はない。したがって
  保存/復元フックはコンテナ内側ではなく、上記のホスト側（オーケストレータ）に置くのが
  素直で、実装コストも低い。
- **セッション ID はコンテナの内外どちらからも同じ値が取れる。** 外側（オーケストレータ）
  では work item のメタデータからコンテナ起動前にわかる（`session_id = work.data.id`）。
  内側（コンテナ）では、オーケストレータが forward している `ANTHROPIC_SESSION_ID`
  環境変数から取得できる（`worker/__main__.py` の docstring 通り、`EnvironmentWorker` は
  この環境変数群からセッション情報を読む）。6.4 の実測で「work item ＝セッションの 1 ラン」
  であることが分かっているため、この `session_id` をキーにホスト側へ
  `workspaces/<session_id>/` のようなディレクトリを持たせれば、同一セッションが idle 後に
  別のコンテナで再開したときの復元判定にそのまま使える。

## 片付け

**アーカイブは取り消せない。実行前に必ず確認すること。** スクリプトからの自動アーカイブは行わない。

| 資源 | 片付け方 |
|---|---|
| Agent | Console または API で `client.beta.agents.archive(agent_id=...)`。**永久に読み取り専用になり、新しいセッションを参照できなくなる。取り消せない。** |
| Environment | `client.beta.environments.archive(environment_id=...)` または `.delete(...)` |
| Vault / credential | `client.beta.vaults.archive(vault_id=...)` または `.delete(...)`（credential ごとの delete/archive も可） |
| Skill | `client.skills.delete(skill_id=...)`（delete のみ、archive はない） |
| Docker | `docker rm -f cma-mode-a-worker`、`docker volume rm cma-mode-a-workspace`、`docker rmi cma-verify-worker:dev` |
| Terraform 資源 | `cd terraform && terraform destroy`（サービスアカウントと IAM バインディングのみ削除。`house_monitor` データセットには触れない） |
| 発行した GCP キー | `gcloud iam service-accounts keys delete <KEY_ID> --iam-account <email>`。`terraform destroy` はこのキーを追跡していないので別途削除が必要 |
| `.provisioned.json` / `secrets/` / `logs/` | ローカルファイルとして手動削除 |

## 制約・スコープ外

- **この検証はセキュリティハードニングを対象としない。** ワーカーコンテナは root で動作し、
  rootfs は read-write、egress 制限もかけていない。本番投入時は利用者の責任で非 root 化・
  rootfs read-only 化・ネットワークポリシーを追加すること。
- **self-hosted Environment では vault の `environment_variable` credential は使えない**
  （Anthropic 側の egress を経由しないため）。GCP キーのような非 MCP の秘密情報は、この検証の
  ように Docker のマウントで供給するか、`agent.custom_tool_use` によるカスタムツール経由で扱う
  必要がある。
- **self-hosted Environment ではリポジトリ内 `.claude/skills` の自動探索は使えない**
  （`file` / `github_repository` リソースが self-hosted では拒否されるため）。skills は
  必ず Skills API 経由でアップロードする。
- ワークスペースの永続化そのもの（モード B の使い捨てコンテナ間でファイルを引き継ぐ仕組み）は
  この変更のスコープ外。`orchestrator/main.py` の `run_one_work_item` に接続点のコメントを残す
  に留める。フックの実装可能性とセッション ID の取得経路については上記「ワークスペース永続化
  に向けた下調べ」を参照。
