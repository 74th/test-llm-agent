# Claude Code Self-hosted Environment 検証

Claude Team/Enterprise の [Self-hosted Environment](https://code.claude.com/docs/en/self-hosted-environments)（public beta）で、独自コンテナ上の runner にマウントしたワークスペースの **skills** と **MCP サーバ（GitHub MCP）** がセッションから実際に見えるかを検証する。設計の背景と根拠は [`openspec/changes/verify-self-hosted-environment/design.md`](openspec/changes/verify-self-hosted-environment/design.md) を参照。このファイルだけで検証を実行できるように、判断の根拠以外の実務手順はすべてここに書く。

## 検証に使うリポジトリ（task 1.5）

**`74th/test-llm-agent`**。GitHub PAT は fine-grained token で、このリポジトリの `Contents: Read-only` のみに絞って発行済み（task 1.4）。

`checkout-probe` の単発検証（task 7.7 / 9.11）には別途、認証不要でクローンできる公開リポジトリを使う。デフォルトで `https://github.com/octocat/Hello-World.git` で動作確認済み。

## claude.ai environment（task 1.2）

- **Environment ID**: `ccpool_01AayutJLzKvu1hTFA9B7fHD`
- Environment secret 本体は `secrets/environment-secret` に保存する（git 管理外。ファイル自体はこのリポジトリに含まれない）。

---

## 構成

### ディレクトリと役割

```
container/
  Dockerfile                # イメージ本体。claude バイナリ・git・gcloud/bq・docker CLI を同梱
  entrypoint.sh              # ワークスペースのコピー + .claude.json 生成 + runner/orchestrator 起動
  session-wrapper.sh         # --exec-path 先。--permission-mode auto を強制
  log-event.sh               # JSONL 追記の共通スクリプト（秘密情報を出力しない）
  hooks/
    spawn-runner              # orchestrator の spawn-runner フック（薄いディスパッチャ）
    post-session               # runner の post-session フック（永続化はしない）
  provisioners/
    docker.sh                  # spawn-runner のバックエンド（検証用、Docker）
    gke.sh.example              # GKE 移行時の雛形（未実装）
  checkout-probe/
    checkout                    # checkout フックの単発検証専用スクリプト
  compose.persistent.yaml     # モード A（常駐）
  compose.ondemand.yaml       # モード B（セッション毎、orchestrator）
  .env.example                # 人間が埋める変数の雛形 → container/.env にコピーして使う
workspace/
  .claude/
    skills/what-is-pentelpantel/SKILL.md   # 検証用スキル
    hooks/ccr-session-event.sh              # セッション内 Claude Code hooks 用スクリプト
    settings.json                            # SessionStart/PostToolUse/Stop/SessionEnd を定義
terraform/
  main.tf / variables.tf / outputs.tf   # nnyn-dev の検証用サービスアカウントと IAM バインディング
secrets/                      # git 管理外。実際の secret ファイルを置く場所（後述）
```

### コンテナ内のマウントとパス

| 項目 | パス | 理由 |
| :-- | :-- | :-- |
| ワークスペース（読取専用） | `/mnt/workspace` | ホストの `workspace/` をそのまま渡す |
| host config ルート | `/opt/claude-config`（`HOME`） | `~/.claude` と `~/.claude.json` がドキュメントの既定レイアウトそのままになる（design.md D1） |
| runner の `--base-dir` | `/var/lib/claude-runner` | 既定値 `/workspace` はリポジトリ側のディレクトリ名と衝突するため回避（design.md D3） |
| GCP 認証情報（読取専用） | `/run/secrets/gcp-sa.json` | ワークスペースの外。`GOOGLE_APPLICATION_CREDENTIALS` で指す |
| イベントログ（読み書き） | `/var/log/ccr-events` | ホスト側の JSONL ログディレクトリ |

entrypoint 起動時に `/mnt/workspace/.claude` を `/opt/claude-config/.claude` へコピーし、その後に GitHub MCP の `.claude.json` を生成する。**この処理は起動時に一度だけ**なので、`workspace/` を編集したらコンテナ再起動が必要（モード A なら `docker compose restart`）。

### モード A（常駐）とモード B（セッション毎）の違い

| | モード A: 常駐 | モード B: セッション毎 |
| :-- | :-- | :-- |
| compose ファイル | `compose.persistent.yaml` | `compose.ondemand.yaml` |
| 常駐するもの | runner コンテナ自体 | orchestrator コンテナのみ |
| セッションの実行場所 | 同一コンテナが複数セッションを継続して拾う | `spawn-runner` フックが要求ごとに使い捨てコンテナを起動 |
| `--drain-grace-sec` | `3600`（正の値、常駐させるため） | 未設定（既定 `0`。1 セッションで終了） |
| environment secret の置き場 | 全 runner ホスト（このコンテナ自身） | orchestrator ホストのみ。runner 自身は単発の work-order JWT しか持たない |
| Docker ソケットへの依存 | なし | あり（`spawn-runner` → `docker.sh` が sibling コンテナを起動するため） |

両モードとも `--capacity 1` と `--use-anthropic-git-proxy` を使う（design.md D4/D5）。git 認証情報をイメージに一切持たせず、セッション作成者の GitHub OAuth トークンでクローンされる。

### イベントログの設計（永続化は未実装）

セッション毎ワークスペースの永続化を実装する前に、**必要なイベントが実際に取れるか**だけを先に確認する。永続化そのものはこの change では実装しない。

イベント面は 2 つ。

**(1) runner レベル**（`--hooks-dir` のライフサイクルフック。runner の外側で動く）

| フック | 発火タイミング | 取れるもの |
| :-- | :-- | :-- |
| `spawn-runner`（モード B のみ） | ワークロード起動要求の直後 | order ID, session ID, repo URL, **`CLAUDE_RUNNER_ACCOUNT_EMAIL` / `CLAUDE_RUNNER_ACCOUNT_ID`（実行者）** |
| `session-wrapper.sh`（`--exec-path`。ログは wrapper 側に自前で仕込む） | セッションの子プロセス起動直前 | session ID, config dir, client platform, **`CCR_SESSION_ACCOUNT_EMAIL`（実行者）** |
| `post-session` | セッション終了後、ワークスペース破棄の**前**。ドキュメント曰く「未コミットの作業を救う唯一の機会」 | 各ワークスペースパスの存在有無・ファイル数・`git status --porcelain` の行数、`CLAUDE_RUNNER_EXIT_REASON`、フック自身の所要ミリ秒、`CLAUDE_RUNNER_ACCOUNT_EMAIL`（未検証・下記参照） |

`post-session` の終了コードはセッション結果に影響しない（失敗しても無視される）ため、成否と所要時間を自前でログに残す設計にしてある。タイムアウトは既定 60 秒（`--post-session-hook-timeout-sec`）。

**実行者（誰がセッションを開始したか）の記録について**: 社内利用では監査上重要なので、実測で確認した。環境変数名を全ダンプして探したところ、次のものが見つかった。

- `CLAUDE_RUNNER_ACCOUNT_EMAIL` / `CLAUDE_RUNNER_ACCOUNT_ID`: runner lifecycle hook（`spawn-runner`）の環境に存在。実測で `spawn_request` イベントに `account_email`/`account_id` として記録されることを確認済み。
- `CCR_SESSION_ACCOUNT_EMAIL`: `session-wrapper.sh` の環境、および Claude Code の子プロセス自体（＝ `workspace/.claude/hooks/ccr-session-event.sh` などセッション内フック）からも見える。`session_start` と `session_hook_*` イベントに `account_email` として記録されることを確認済み。
- `CLAUDE_CODE_ACCOUNT_UUID` / `CLAUDE_CODE_ORGANIZATION_UUID`: セッション内（Claude Code 自身のプロセス環境）にも存在するが、今回はメールアドレスの方が監査目的に直接使えるため未採用。

これで `spawn_request`・`session_start`・`session_hook_*` の3イベント全てに実行者のメールアドレスが記録されるようになった。`post-session` 側は `CLAUDE_RUNNER_ACCOUNT_EMAIL` が同じく取れるはずという想定で実装済みだが、実機での確認はまだ（次にセッションが正常終了した時点で `events.jsonl` の `post_session_start` を見て検証する）。

**(2) セッション内**（Claude Code hooks。セッション child プロセスの中で動く）

`workspace/.claude/settings.json` に `SessionStart` / `PostToolUse` / `Stop` / `SessionEnd` を定義し、いずれも `workspace/.claude/hooks/ccr-session-event.sh` を呼ぶ。runner が異常終了して `post-session` が発火できない場合の代替経路として、こちらが動くことを確認する。

**排他関係・置き換え関係の注意**

- `--exec-path`（`session-wrapper.sh`）を設定すると、lifecycle hook の `command` は**無視される**。セッション開始のログは wrapper 側にしか書けない。
- `checkout` フックは組み込みのクローンを**置き換える**。`--use-anthropic-git-proxy` はこの組み込みクローン経路に依存するため、`checkout` フックを常設すると git プロキシ経由の認証が成立しない。したがって `checkout-probe/checkout` は本編の 2 モードには入れず、単発検証専用とする（下記「9. 実機検証」参照）。

ログは `/var/log/ccr-events/events.jsonl` に 1 行 1 JSON で追記される。共通フィールドは `ts` / `event` / `session_id`。work-order JWT・セッショントークン・GitHub PAT・SA キーの値はどのログ経路にも出力しない（`log-event.sh` の呼び出し側が値を渡さない設計。task 7.2 で確認済み）。実行者のメールアドレス（`account_email`）だけは監査目的で意図的に記録している（下記「実行者の記録について」参照）。個人情報なので、このログを永続化・共有する場合は取り扱いに注意する。

**セッション識別子の対応関係（同一セッションだと判別できる情報）**

実機検証中、`session_id` フィールドの中身が呼び出し元によって異なる ID 体系であることが分かった。3 種類ある。

| 識別子 | 出どころ | 例 | 再接続・再スポーンを跨いで安定か |
| :-- | :-- | :-- | :-- |
| `cse_<suffix>` / `session_<suffix>`（同じ suffix） | runner の `session_start` ログの `config_dir`、`post-session`/`spawn-runner` フックの `session_id` | `cse_01Q1RSycGLU3uR1DZcHpbWr2` | **安定**。claude.ai 側が会話に対して発行する ID で、runner プロセスやコンテナに紐付かない |
| Claude Code 内部の hook session_id（`$CLAUDE_SESSION_ID`） | `workspace/.claude/settings.json` 経由の `session_hook_*` イベント（SessionStart/PostToolUse/Stop/SessionEnd） | `3f86b61b-2790-532f-9302-68a1e74dab8f` | **安定**（実測）。同じ `cse_` ID に対しては再起動を挟んでも同じ値になった。おそらく `cse_` ID から決定的に導出されている。セッション**内側**（skill/hook）から見える唯一の識別子 |
| `order_id`（モード B の spawn 試行 ID）、コンテナ名 `ccr-<order_id>` | `spawn-runner` フック、`spawn_request` イベント | `c1374370-c7bf-574e-a5b3-534e2e5322e3` | **不安定**。同一セッションへの再送・リトライでも毎回別の値になる。spawn 試行 1 回を識別するだけで、セッションの識別には使えない |

実測例（`compose.ondemand.yaml` のワークスペースマウント漏れバグで同一セッションが 6 回リトライされた際のログ。バグの詳細は下記「気づいた点」参照）:

```
spawn_request session_id=session_01Q1RSycGLU3uR1DZcHpbWr2 order_id=c1374370-... attempt=2
spawn_request session_id=session_01Q1RSycGLU3uR1DZcHpbWr2 order_id=40e83daf-... attempt=3
spawn_request session_id=session_01Q1RSycGLU3uR1DZcHpbWr2 order_id=be94cc20-... attempt=6
```

`order_id` は試行ごとに変わるが `session_id`（`cse_`/`session_` 系）は一貫している。また、モード A のコンテナをイメージ再ビルドで作り直した際も、同じ `cse_01Q1RSycGLU3uR1DZcHpbWr2` に runner が再接続し、`RegisterWorker -> 200 worker_epoch=3`（再アタッチのたびに増加）とともにトランスクリプトが再水和された（`transcript_hydrated messages=104`）。

**制約**: 現状の `log-event.sh` 呼び出しでは、runner 側イベント（`session_start`/`spawn_request`/`post_session_*`）には (1) の `cse_`/`session_` ID が、セッション内イベント（`session_hook_*`）には (2) の内部 ID しか記録されない。両者を同一ログ行で突き合わせる仕組みは無く、タイムスタンプの前後関係で人力突合するしかない。

### spawn の 2 層構造（モード B）

`spawn-runner`（`${hooks-dir}/spawn-runner`。Anthropic 側の契約を引き受ける薄いディスパッチャ）と `provisioners/*.sh`（実際にワークロードを起動するバックエンド）を分離してある。

**内部契約**（ディスパッチャ → バックエンド。プロビジョナ非依存）

| 渡し方 | 名前 | 内容 |
| :-- | :-- | :-- |
| stdin | — | work-order JWT（1 行）。引数にも環境変数にも置かない |
| env | `SPAWN_ORDER_ID` | 冪等キー。リソース名として安全な文字列 |
| env | `SPAWN_RUNNER_IMAGE` | 起動するイメージ |
| env | `SPAWN_RUNNER_ARGS` | runner に渡す引数列 |
| env | `SPAWN_RUNNER_MOUNTS` | `<source>:<container-path>:<ro\|rw>` の空白区切りの並び |
| env | `SPAWN_SESSION_ID` | ログ用。pre-warming 要求では空 |

バックエンドが守る 3 規約:

1. **`SPAWN_ORDER_ID` で冪等**（同じ ID の再配信で起動するワークロードは高々 1 つ）
2. **リトライしない**（1 order = 高々 1 ワークロード）
3. **終了コード**: `0` = 投入済み、`1` = リトライ可能な失敗、`2` 以上 = リトライ不可

GKE へ移行する場合は `provisioners/gke.sh.example` のコメントを埋めるだけで済む設計（`spawn-runner` 自体は変更不要）。

---

## 人間が設定すべき内容

以下はブラウザ操作や外部サービスへのアクセスが必要で、自動化できない。チェックリストとして使う。

| # | 作業 | 必要なロール | 保存先 / 渡し方 |
| :-- | :-- | :-- | :-- |
| 1 | [Cloud environments](https://claude.ai/admin-settings/cloud-environments) で **Allow self-hosted environments** を有効化 | Organization Owner | — |
| 2 | environment を作成し、**Copy environment key** で environment secret を取得 | Owner | `secrets/environment-secret`（0600, git 管理外）。あわせて `ccpool_...` 形式の environment ID を控える。**key は一度しか表示されない** |
| 3 | 組織の GitHub 連携が有効なことを確認 | Owner or Member | — |
| 4 | GitHub MCP 用の PAT を発行（最小スコープ。リポジトリ読み取りのみで足りる想定） | GitHub アカウント所有者 | `container/.env` の `GITHUB_PAT`（git 管理外） |
| 5 | 検証に使うリポジトリを 1 つ決める | — | このファイルの「検証に使うリポジトリ」欄に記入 |
| 6 | ホスト時刻が NTP 同期していること（ずれ 5 分未満）、Docker が使えることを確認 | ホスト管理者 | — |
| 7 | `nnyn-dev` に対する `terraform apply` 権限があることを確認 | GCP プロジェクト管理者 | — |
| 8 | `terraform apply`（下記「検証手順」参照）の後、`gcloud iam service-accounts keys create` でサービスアカウントキーを発行 | GCP プロジェクト管理者 | `secrets/gcp-sa.json`（0600, git 管理外） |

```bash
# 手順8: terraform apply 後に実行
gcloud iam service-accounts keys create secrets/gcp-sa.json \
  --iam-account=test-claude-self-hosted-env@nnyn-dev.iam.gserviceaccount.com
chmod 600 secrets/gcp-sa.json
```

**キーを Terraform で作らない理由**: `google_service_account_key` リソースはプライベートキーを平文で tfstate に書き込む。tfstate は多くの場合 CI のログやバックエンドストレージに残るため、キー発行は人間の手作業（`gcloud iam service-accounts keys create`）に限定し、Terraform の管理対象から外している（design.md D11）。

**各シークレットのコンテナへの渡し方**

| シークレット | 渡し方 |
| :-- | :-- |
| environment secret | Docker secret ファイル（`--environment-secret-file` / compose の `secrets:`） |
| GitHub PAT | 環境変数 `GITHUB_PAT`（entrypoint が実行時に `.claude.json` を生成する材料としてのみ使う。イメージにも `workspace/` にも焼き込まない） |
| GCP サービスアカウントキー | 読み取り専用マウント（`/run/secrets/gcp-sa.json:ro`）+ `GOOGLE_APPLICATION_CREDENTIALS` |

`container/.env.example` を `container/.env` にコピーし、上記を埋める:

```bash
cp container/.env.example container/.env
# container/.env を編集: GITHUB_PAT, ENVIRONMENT_SECRET_FILE, GCP_SA_KEY_PATH, CCR_EVENT_LOG_DIR
```

`GCP_SA_KEY_PATH` と `CCR_EVENT_LOG_DIR` は**絶対パスで指定する**こと。モード B は `docker.sock` を経由してホストの Docker デーモンにセッションコンテナを起動させるため、これらのパスはオーケストレータコンテナ自身のファイルシステムではなくホストのファイルシステムとして解釈される。

---

## 検証手順

各手順の先頭に、コマンドで済むか（`[cmd]`）claude.ai の画面操作が必要か（`[web]`）を示す。

### 0. Terraform（GCP サービスアカウント）— 一度だけ実行

```bash
# [cmd]
cd terraform
terraform init
terraform plan   # SA 作成 + IAM バインディング2つだけが出ることを確認。テーブル自体の変更が出ないことを確認
terraform apply
```

```bash
# [cmd] 人間の作業(表8の項目8)
gcloud iam service-accounts keys create ../secrets/gcp-sa.json \
  --iam-account=$(terraform output -raw service_account_email)
chmod 600 ../secrets/gcp-sa.json
```

```bash
# [cmd] 発行したキーでアクセス確認（対象テーブルは読める）
CLOUDSDK_CONFIG=$(mktemp -d) gcloud auth activate-service-account \
  test-claude-self-hosted-env@nnyn-dev.iam.gserviceaccount.com \
  --key-file=../secrets/gcp-sa.json
CLOUDSDK_CONFIG=<同じ一時ディレクトリ> bq query --use_legacy_sql=false --project_id=nnyn-dev \
  'SELECT COUNT(*) FROM `nnyn-dev.house_monitor.co2` WHERE timestamp >= TIMESTAMP("2000-01-01")'

# 別データセットは拒否されることを確認
CLOUDSDK_CONFIG=<同じ一時ディレクトリ> bq ls --project_id=nnyn-dev nnyn-dev:picow_test
# => Access Denied で終了すること
```

### 1. claude.ai 側の準備（[web] + [cmd]）

1. `[web]` [Cloud environments](https://claude.ai/admin-settings/cloud-environments) で **Allow self-hosted environments** を有効化
2. `[web]` environment を作成し、environment key をコピーして `secrets/environment-secret` に保存

   ```bash
   # [cmd]
   (umask 077 && cat > secrets/environment-secret)
   # ペースト後 Enter → Ctrl-D
   ```
3. `[web]` GitHub 連携が有効なことを確認
4. `[web]` GitHub PAT を発行し、`container/.env` の `GITHUB_PAT` に設定

### 2. イメージのビルド（[cmd]、両モード共通）

```bash
cd container
cp .env.example .env   # 未実施ならここで
# .env を編集: GITHUB_PAT / ENVIRONMENT_SECRET_FILE / GCP_SA_KEY_PATH / CCR_EVENT_LOG_DIR
docker build --build-arg CLAUDE_CODE_VERSION=$(grep CLAUDE_CODE_VERSION .env | cut -d= -f2) \
  -t claude-self-hosted-runner:verify .
```

### 3. モード A（常駐）

```bash
# [cmd]
cd container
docker compose -f compose.persistent.yaml up -d
docker compose -f compose.persistent.yaml logs -f
# ログに "Registering as opted in to Anthropic-managed git" の後、登録成功が出ることを確認
```

```bash
# [web] claude.ai の Cloud environments で、この environment が Healthy になっていることを確認
```

```bash
# [cmd] 停止・片付け
docker compose -f compose.persistent.yaml down
```

### 4. モード B（セッション毎 / orchestrator）

モード A を先に止めてから実行する（同じ environment secret を同時に2箇所で使わない）。

```bash
# [cmd]
cd container
docker compose -f compose.persistent.yaml down   # モードAが動いていれば
docker compose -f compose.ondemand.yaml up -d
docker compose -f compose.ondemand.yaml logs -f
# "spawn-runner hook found" が出ることを確認
```

```bash
# [web] claude.ai からセッションを開始し、実際に spawn されることを確認
```

```bash
# [cmd] セッション実行中のコンテナを確認
docker ps --filter "name=ccr-"
```

```bash
# [cmd] 停止・片付け
docker compose -f compose.ondemand.yaml down
docker ps -a --filter "name=ccr-" -q | xargs -r docker rm -f
```

### 5. checkout-probe（単発検証。本編の2モードには戻さない）

`checkout` フックは `--use-anthropic-git-proxy` と両立しないため、別途単独で動作確認する。

```bash
# [cmd]
docker run --rm \
  -e CLAUDE_RUNNER_REPO_URL=https://github.com/octocat/Hello-World.git \
  -e CLAUDE_RUNNER_CHECKOUT_PATH=/tmp/checkout-out \
  -e CLAUDE_RUNNER_SESSION_ID=manual-probe \
  -v "$(pwd)/../secrets/events:/var/log/ccr-events:rw" \
  --entrypoint /opt/claude/checkout-probe/checkout \
  claude-self-hosted-runner:verify
# exit 0 と、checkout_probe イベントがログに残っていることを確認
```

---

## 人間が検証すべき内容

claude.ai でセッションを開始し、以下の 5 プロンプトを**そのままコピーして**貼り付ける。判定条件を満たせば合格。両モードで実施し、下記の結果マトリクスに記録する。

### (a) skill の列挙

> このセッションで使える skill を一覧で教えてください。

**合格条件**: `what-is-pentelpantel` が一覧に含まれる。

### (b) skill の内容確認

> ペンテルパンテルとは何ですか?

**合格条件**: 「74th が作成した自作キーボード」「左右の手と中央のテンキーで3分割」のような、SKILL.md の内容に基づく回答が返る（skill を実際に読み込んで使えている証拠になる）。

### (c) MCP tool の列挙

> 利用可能なMCPツールを一覧で教えてください。

**合格条件**: `github` サーバ由来のツール（例: リポジトリ検索、issue 取得など）が含まれる。含まれない場合は runner のログ（`--log-level debug`）で `.claude.json` のどちらの配置が読まれたかを確認する（下記「切り分け手順」）。

### (d) GitHub MCP 経由のリポジトリ情報取得

> GitHub MCPツールを使って、このセッションのリポジトリの最新のコミット情報を教えてください。

**合格条件**: 実際に GitHub MCP のツール呼び出しが発生し、コミット情報が返る（ツール呼び出しログで確認できる）。

### (e) 実行場所の証明（BigQuery アクセス、既製スクリプトは渡さない）

> このコンテナ内で使える認証情報とツールを使って、BigQueryのテーブル `nnyn-dev.house_monitor.co2` にアクセスするスクリプトをその場で書いて実行し、テーブルの行数を教えてください。

**合格条件**: Claude が `bq` または `google-cloud-bigquery` 等を使うスクリプトを自分で書いて実行し、行数（terraform apply 直後の実測値は 78303 行。データが追加され得るため厳密一致は不要）を答える。

このテーブルの認証情報（`GOOGLE_APPLICATION_CREDENTIALS`）は**このコンテナにしか存在しない**ため、正しい行数が返ってくることは、そのセッションが実際にこのコンテナ内のリソースで動いていることの証明になる。既製のスクリプトを渡さずその場で書かせるのは、Claude が単に事前に用意された結果を読み上げているのではなく、実際にコンテナ内のツールチェーン（`bq`/`gcloud`/Python 等）と認証情報を使って到達したことを確認するため。

---

## 結果マトリクス

| 確認項目 | モード A | モード B |
| :-- | :-- | :-- |
| (a) skill 列挙 | 成功（`what-is-pentelpantel` が一覧に含まれた） | 成功（同一結果） |
| (b) skill 内容 | 成功（ペンテルパンテルの説明に正しく回答） | 成功（同一結果） |
| (c) MCP tool 列挙 | 成功（`mcp__github__*` 等の GitHub MCP ツールが列挙された） | 成功（同一結果） |
| (d) GitHub MCP 経由取得 | 成功（GitHub MCP 経由でコミット情報を取得） | 成功（同一結果） |
| (e) BigQuery 実行場所証明 | 成功（テーブルへのアクセス・行数取得に成功）。ただしコンテナに Python が無く、`bq show` コマンドにフォールバックして試行錯誤していた（下記「気づいた点」参照） | 成功（同一結果） |
| runner 登録成功 / Healthy | 成功（`RegisterRunner -> 200 runner_id=ccrunner_01NNRkqMjogpRxCg2GeScujL`。claude.ai UI で Healthy 表示を確認済み） | 成功（`/healthz` が `{"status":"ok", "connected":true, ...}` を返した。claude.ai UI 上は on-demand のため待機中は「No runners deployed / 0 active sessions」と表示されるのが正常。セッション開始後は `pool_active_session_count` が増加することを確認） |
| 2セッション目のセッション継続（A）/ 個別コンテナ起動（B） | 未実施 | 成功（2つのセッションそれぞれで別々の `order_id` に対して個別のコンテナ ccr-f8b2c44e-... / ccr-c4fcef47-... が起動した） |
| イベントログ: 起動要求→開始→終了が時系列で追える | 成功（`session_start`→複数回`session_hook_PostToolUse`（1セッションあたり12回/5回）→`session_hook_Stop`→`session_hook_SessionEnd`→`post_session_start`/`post_session_end`が時系列で確認できた） | 未実施 |
| `.claude.json` は「隣」/「中」のどちらで認識されたか | 「中」（`/opt/claude-config/.claude/.claude.json`）。起動ログ: `host config snapshot (disk): 3 file(s), 1.8 KiB from /opt/claude-config/.claude → ..., 1 mcpServer(s)` | 未確認 |

凡例: 成功 / 失敗 / 未実施。人間による claude.ai 操作（1.1〜1.4）が完了したら、上表と `## 検証結果の記録` を実測値で更新する。

---

## 切り分け手順

- **runner が登録できない**: `docker compose logs` を確認。`[runner:fatal] RegisterRunner auth failed` は environment secret が無効/失効。`environment secret is missing the ccr:pool_id claim` は secret ファイルの内容が JWT として不正（コピー時の欠落や改行の混入を疑う）。
- **`.claude.json` の向き先確認**: `--log-level debug` で起動し、host config のスナップショット処理と MCP 設定読み込みのログ行を探す。ログに現れたパスが `/opt/claude-config/.claude.json`（隣）か `/opt/claude-config/.claude/.claude.json`（中）かを確認し、上の結果マトリクスに記録する。
- **MCP エントリが認識されない**: runner はセッション起動時に、認識できなかった `mcpServers` エントリについて警告ログを出す（`type` が不明な値など）。debug ログでその警告行を探す。
- **BigQuery アクセス失敗の見分け方**:
  - **資格情報が届いていない**: セッション内で `echo $GOOGLE_APPLICATION_CREDENTIALS` や `gcloud auth list` がエラー、またはファイルが存在しない → マウント設定を確認（`docker inspect` でボリュームを確認)。
  - **権限不足**: `gcloud`/`bq` が `403 Permission denied` を明示的に返す → IAM バインディング（`terraform plan` の内容）を確認。
  - **egress 遮断**: タイムアウトや DNS 解決失敗 → `oauth2.googleapis.com` / `bigquery.googleapis.com` への到達性を確認。

---

## 検証用途限定に関する注記

以下はこの検証環境固有の簡略化であり、**本番環境にそのまま転用しない**こと。

- **`--permission-mode auto` を wrapper で固定**している。ドキュメントは auto モードの固定を default-deny egress とセットで推奨しているが、本検証では egress 制限を行っていない。
- **Docker ソケットをオーケストレータコンテナにマウント**している（モード B）。これは実質的にホストへの root 権限に等しい。実運用では `provisioners/gke.sh` 相当への切り替えでソケットマウント自体が不要になる。
- **default-deny egress は適用していない**。セッションが到達できるホストに制限を設けていない。
- **全セッションが同一ワークスペースを共有する**。本来はセッション毎に新しいワークスペースを構築すべきだが、今回は省略している（ユーザ合意済み）。

## 片付け手順

```bash
# コンテナとイメージの削除
cd container
docker compose -f compose.persistent.yaml down 2>/dev/null
docker compose -f compose.ondemand.yaml down 2>/dev/null
docker ps -a --filter "name=ccr-" -q | xargs -r docker rm -f
docker rmi claude-self-hosted-runner:verify

# GCP: サービスアカウントとキーの削除
cd ../terraform
terraform destroy
# なお、鍵を先に失効させる場合:
# gcloud iam service-accounts keys list --iam-account=test-claude-self-hosted-env@nnyn-dev.iam.gserviceaccount.com
# gcloud iam service-accounts keys delete <KEY_ID> --iam-account=...

# secrets/ の削除
rm -rf secrets/
```

加えて、`[web]` claude.ai の Cloud environments で作成した environment を削除し、GitHub PAT を失効させる。

---

## 検証結果の記録

_人間側のセットアップ（claude.ai の operations、GitHub PAT 発行）完了後、以下を実施して記録する。_

- 検証時の Claude Code バージョン: `2.1.278`（イメージビルド時点でホストにインストールされていたバージョンを採用。実際の検証時にバージョンが変わっていれば更新する）
- 両モードの結果差分:
- 永続化の実装可否の判断（どのイベントで何が救えたはずか）:

### モード B: orchestrator 起動確認（task 6.5）

- Mode A のコンテナを停止した状態で `compose.ondemand.yaml` を起動し、`/healthz` が `{"status":"ok", ..., "pool_id":"ccpool_01AayutJLzKvu1hTFA9B7fHD", "connected":true, ...}` を返すことを確認した。
- 起動直後、待機中だったセッションに対して orchestrator が自動的に `spawn-runner` フック経由でセッションコンテナ（`ccr-c1374370-...`）を1つ起動したことをログで確認した（`docker.sh: started ccr-...`）。

### 気づいた点（task 9.1、モード A）

- コンテナ内に Python が無く、(e) の実行時に Claude が Python を探して試行錯誤したのち `bq show` コマンドにフォールバックして目的を達成した。結果自体は正しかったが、遠回りだった。
- 対応済み: `container/Dockerfile` に `uv` を追加（`uv run --with google-cloud-bigquery script.py` のようにライブラリを都度指定してPythonスクリプトを実行できる）。また `workspace/.claude/skills/container-toolchain/SKILL.md` を追加し、`bq`/`gcloud`/`uv` が使える旨をセッションに明示した。イメージ再ビルド・Mode A 再起動済みで、`uv 0.12.17` の動作と両 skill（`container-toolchain`, `what-is-pentelpantel`) のコンテナ内存在を確認済み。
