# Design

## Context

動機は proposal.md - Why を参照。プロジェクトは実装コードをまだ持たない greenfield で、現状は OpenSpec のスキャフォールドと `run_claude_in_sbx.sh` のみ。

Managed Agents のプラットフォーム制約が設計をほぼ決めている。

- 「独自コンテナ環境」に対応するのは Environment の `config: {type: "self_hosted"}`。エージェントループは Anthropic 側に残り、`bash` / ファイル系ツールだけが自前コンテナに移る。接続は outbound のみ（ワーカーがワークキューを long-poll する）。
- self-hosted では `file` / `github_repository` リソースが使えない。したがってリポジトリ直下 `.claude/skills` の自動探索は利用できず、skills は Skills API へのアップロード経由で Agent に添付するしかない。
- self-hosted では vault の `environment_variable` credential が使えない（egress が Anthropic 側にないため）。GCP キーは Docker のマウントで渡す。MCP の認証情報は vault で扱える（MCP は Anthropic 側で実行される）。
- ワーカーヘルパー（`EnvironmentWorker` / work poller）が存在するのは Python / TypeScript / Go のみ。Python を採用。
- MCP は URL（Streamable HTTP）形式のみ。ローカルの stdio サーバは扱えない。検証対象は GitHub の hosted MCP。
- `web_search` / `web_fetch` は環境種別に関わらず Anthropic 側で実行される。この検証では無効化し、「コンテナ内で作業している」ことの判定を曖昧にしない。

## Goals / Non-Goals

**Goals:**

- 2 つのワーカー起動方式を、同じ Agent / Environment / skills / MCP 構成のまま切り替えて検証できるようにする。
- コンテナのライフサイクルを、後からワークスペース永続化を差し込める 1 か所に集約する。
- 検証結果が「コンテナ内で実行された」ことを否定できない形で出るようにする（マウントしたキーでしかできない作業をやらせる）。

**Non-Goals:**

- ワークスペースの永続化そのもの（イベントが取れることの確認までに留める）。
- コンテナのセキュリティハードニング（非 root 化、rootfs read-only、egress 制限）。検証用であり、README に「本番では利用者責任」と注意を書くに留める。
- メモリストア、マルチエージェント、スケジュール実行、outcome/rubric の検証。
- MCP サーバの自作・ホスティング。

## Decisions

### D1. ワーカーは Python SDK の `EnvironmentWorker` を使う（`ant` CLI ワーカーではない）

`ant beta:worker poll` は固定ツールセットで手軽だが、Python SDK の `EnvironmentWorker` を使うことでモード A の常駐ループ（`run()`）とモード B の単発処理（`handle_item()`）を同一のコードベース・同一イメージで表現できる。イメージが 1 つで済み、両モードの差がエントリポイントの引数だけになる。

代替案: `ant beta:worker poll --on-work spawn.sh`。シェルだけでモード B が組めるが、ライフサイクルログを `spawn.sh` に書くことになり、`ANTHROPIC_WORK_SECRET` を stdin の JSON から自前で取り出す必要があり、モード A とコードを共有できない。採用しない。

### D2. モード B のポーリングはホスト側の Python オーケストレータが行う

`client.beta.environments.work.poller(...)` を `auto_stop=False` で回し、`work.data.type == "session"` の item ごとに `docker run` する。起動するコンテナのエントリポイントは `EnvironmentWorker(...).handle_item()`（引数なし、環境変数から ID を解決）。`auto_stop=False` は、停止シグナルの送出を起動されたコンテナ側に任せるため。

渡す環境変数は `ANTHROPIC_SESSION_ID` / `ANTHROPIC_WORK_ID` / `ANTHROPIC_ENVIRONMENT_ID` / `ANTHROPIC_ENVIRONMENT_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_WORK_SECRET`。値は `docker run -e KEY=VALUE` ではなく親プロセスの環境に入れて `-e KEY`（値なし）で引き渡し、`ps` に秘密が出ないようにする。

### D3. ライフサイクルログは JSON Lines、追記専用、フラッシュ即時

`logs/container-lifecycle.jsonl` に 1 イベント 1 行で追記する。イベントは `container_start` / `container_exit` / `container_start_failed`。共通フィールドは `event` / `ts`（UTC ISO 8601）/ `session_id` / `work_id` / `environment_id` / `container_name`、`container_exit` は加えて `exit_code` / `duration_ms` / `error`。

対応付けはコンテナ名を `cma-<work_id>` の形で決定的に組むことで担保する。書き込みは 1 関数（`log_event`）に集約し、その呼び出し位置の直前・直後がそれぞれ「ワークスペース復元フック」「ワークスペース保存フック」の予定地であることをコメントで明示する（`container-lifecycle-log` spec の永続化フック要件）。

`try` / `finally` で `container_exit` を必ず書く。オーケストレータの SIGTERM はフラグにしてポーリングループを抜け、in-flight のコンテナの終了を待ってから終了する。

代替案: Docker のイベント API（`docker events`）を購読する。コンテナ側の事実に忠実だが、session ID との対応付けを別途取る必要があり、オーケストレータが知っている情報をそのまま書くより複雑。採用しない。

### D4. イメージは 1 つ、モードはエントリポイントの引数で切り替える

`docker/Dockerfile` は `python:3.12-slim` ベース（`/bin/bash` が SDK ヘルパーの要件）。Anthropic SDK と `google-cloud-bigquery` を入れ、`worker/` をコピーする。`python -m worker <run|handle-item>` で分岐する。

検証用マーカーとして、ビルド時に `/etc/cma-verification-marker` にイメージ識別子・ビルド時刻を書き込む。エージェントにこれを読ませることで実行場所が一意に確定する（`self-hosted-environment` spec）。

`/workspace` を作業ディレクトリにする。モード A では named volume をマウントして「状態が持ち越される」ことを示し、モード B では何もマウントせず「持ち越されない」ことを示す。この差が永続化が必要だという結論の根拠になる。

### D5. GCP キーは読み取り専用マウント + `GOOGLE_APPLICATION_CREDENTIALS`

ホスト側の `secrets/gcp-sa-key.json` を `/run/secrets/gcp-sa-key.json:ro` にマウントし、`GOOGLE_APPLICATION_CREDENTIALS` をそのパスに設定する。イメージには焼き込まない。`secrets/` は `.gitignore` に入れる。

BigQuery のクライアントライブラリはイメージに入れておくが、**クエリスクリプトは置かない**。エージェントがその場で書くことが検証項目そのものであるため（`bigquery-access-verification` spec）。

### D6. プロビジョニングは冪等なスクリプト 1 本、ID は `.provisioned.json` に保存

`scripts/provision.py` が Environment → skills → vault/credential → Agent の順に処理し、ID を `.provisioned.json`（gitignore 対象）に書く。既に ID があれば Agent は `create` ではなく `update` して新バージョンを払い出す。Environment と vault も同様に再利用する。

Agent 側の構成:

- `model`: `claude-opus-5`（設定で上書き可）
- `tools`: `agent_toolset_20260401` で `web_search` / `web_fetch` を `enabled: false`、残りは `always_allow`。加えて `mcp_toolset`（`mcp_server_name` は `mcp.json` の名前）
- `mcp_servers`: `mcp.json` から生成
- `skills`: アップロードしたカスタムスキルの ID

`mcp.json` のスキーマは Managed Agents の制約に合わせて `{"mcpServers": {"<name>": {"type": "url", "url": "https://..."}}}` とし、`type` が `url` でない、または `command` を持つ宣言は明示的なエラーで弾く（`agent-provisioning` spec）。

MCP の権限ポリシーは既定（`always_ask`）のままにする。承認フローが動くことも検証項目に含まれ、`auto` は人間のチェックポイントにならないため検証の意図に合わない。

### D7. 検証ドライバはセッションを作って SSE を読む 1 本のスクリプト

`scripts/run_verification.py` が Agent を参照するセッションを作り、`vault_ids` を渡し、イベントストリームを読みながら検証用のプロンプトを順に投げる。

- 再接続時は `events/stream` を開いた後に `events` を取得してイベント ID で重複排除する（SSE にリプレイがないため、未解決の `tool_confirmation` を取りこぼすとセッションがデッドロックする）。
- `agent.mcp_tool_use` に対しては `user.tool_confirmation` を返す。`tool_use_id` はイベント ID（`sevt_...`）であり `toolu_...` ではない。
- 終了判定は `session.status_idle` の `stop_reason` を見る。`requires_action` は「まだ何か返すべき」であり終了ではない。
- 投げるプロンプトはシナリオ単位（マーカー読み取り / スキル列挙 / スキル実行 / MCP ツール列挙 / MCP ツール実行 / BigQuery）。モード B ではこれが複数ターンになり、そのままコンテナ起動回数の検証になる。

### D8. Terraform はサービスアカウントとバインディングのみを管理する

`terraform/` に `google_service_account` と、プロジェクトレベルの `roles/bigquery.jobUser`（クエリ実行）、データセットレベルの `roles/bigquery.dataViewer`（対象データの読み取り）を作る。既存の `house_monitor` データセットと `co2` テーブルは Terraform の管理対象にせず、データセットへのバインディングは `google_bigquery_dataset_iam_member` で既存データセットに追記する形にする（`google_bigquery_dataset_iam_binding` は他のメンバーを消すため使わない）。

キーの発行は Terraform では行わず、`gcloud iam service-accounts keys create` で人間が行う手順を README に書く。理由: キーマテリアルが tfstate に平文で残るのを避ける。Terraform の出力はサービスアカウントのメールアドレスに留める。

代替案: テーブルレベルの `google_bigquery_table_iam_member`。より狭いが、テーブルを Terraform の参照に含める必要があり、`co2` テーブルのスキーマ変更と競合しうる。データセットレベルで十分に狭いため採用しない（プロジェクト全体の dataViewer は付けない、が要件）。

### D9. Skills API の呼び出し形（アップロードの具体形）は実装時に確定する

Skills API のエンドポイント（`POST /v1/skills`、`POST /v1/skills/{id}/versions`）は確定しているが、Python SDK での引数の形（ディレクトリの zip 化が必要か、ファイル列挙で渡すか）はこの計画時点の手元資料に含まれていない。実装の最初のタスクで公式ドキュメント（Skills Guide）または SDK の型定義から確定させる。仕様（`agent-provisioning`）は「アップロードされ、Agent に添付され、エージェントが認識する」という観測可能な振る舞いで書いてあるため、どちらの形でも spec は変わらない。

## Risks / Trade-offs

- **Skills API の引数形が想定と違い、アップロード実装が膨らむ** → D9 の通り実装の最初に確定させる。`SKILL.md` 1 枚の最小スキルにしておき、複数ファイル・スクリプト同梱は試さない。
- **GitHub hosted MCP が PAT ではなく OAuth を要求する可能性** → MCP の認証は OAuth bearer が一般的で、サービスのネイティブ API キーが通らないことがある。まず `static_bearer` credential として PAT を登録して試し、通らなければ MCP サーバ側のドキュメントに従って OAuth トークンを取得し `mcp_oauth` に切り替える。どちらでも「MCP が認識される」検証は成立する（ツール列挙は認証前でも可能なため、認証で詰まっても検証項目 3 の主眼は達成できる）。
- **モード B でターン数とコンテナ起動回数が 1:1 にならない** → work item の粒度は「セッションの 1 ラン」であり、エージェントが 1 ターン内で複数回ツールを呼んでもコンテナは 1 つ。この対応関係自体が検証したい事実なので、README には「1 ターン = 1 コンテナ」を期待値として書き、実測が違えばログがその証拠になる、という書き方にする。
- **environment key の漏洩は Anthropic 側から即時失効できない** → キーは `.env`（gitignore 対象）に置き、ログに出さず、`ANTHROPIC_API_KEY` はワーカーホストに置かない（組織スコープの資格情報をエージェントのツール実行に晒さないため、Anthropic の指針どおり）。監視・制御系の呼び出しはワーカーホスト外から行う。
- **Terraform の適用に人間の GCP 権限が必要で、エージェントからは完結しない** → 検証手順を「人間が Terraform を適用してキーを置く」→「以降は自動」の 2 段に分け、README の事前設定として明記する。
- **アーカイブは取り消せない** → 片付け手順に注意として明記し、スクリプトから自動でアーカイブはしない。

## Migration Plan

新規追加のみで既存の振る舞いに影響しない。片付けは README の手順（Agent / Environment / vault / skill のアーカイブ、Terraform の `destroy`、発行したキーの削除）に従う。

## Open Questions

- モード A の常駐コンテナで複数セッションを並行実行したときの挙動（同一 `/workspace` の競合）は、この検証の範囲では 1 セッションずつの逐次実行で確認する。並行時の分離が必要かは、永続化の設計時に改めて判断する。
