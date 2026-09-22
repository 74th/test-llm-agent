# Tasks

## 1. 下調べと足場

- [ ] 1.1 Skills API の Python SDK での呼び出し形（スキルの作成とバージョン追加で、ディレクトリ/zip/ファイル列挙のどれを渡すか）を公式ドキュメントまたは SDK の型定義から確定し、確定した形を design.md の D9 に追記して検証する
- [ ] 1.2 `pyproject.toml`（または `requirements.txt`）を作成して `anthropic` / `google-cloud-bigquery` / `docker` 不要な依存を含めずに定義し、ローカルで依存インストールが成功することを確認する
- [ ] 1.3 `.gitignore` に `secrets/`、`.env`、`.provisioned.json`、`logs/`、`terraform/.terraform*`、`*.tfstate*` を追加し、`git status` にこれらが現れないことを確認する
- [ ] 1.4 設定読み込みモジュール（環境変数と `.provisioned.json` の読み書き）を実装し、必須項目が欠けている場合に項目名と設定方法を含むエラーで終了することをユニットテストで確認する（agent-provisioning: プロビジョニングの前提チェック）

## 2. コンテナイメージとワーカー

- [ ] 2.1 `docker/Dockerfile` を作成し、`python:3.12-slim` ベースで `/bin/bash` が存在すること、ビルド時に `/etc/cma-verification-marker` にイメージ識別子とビルド時刻が書かれることを、ビルド後の `docker run --rm <image> cat /etc/cma-verification-marker` で確認する
- [ ] 2.2 `worker/__main__.py` に `run` / `handle-item` の 2 サブコマンドを実装し（`run` は `EnvironmentWorker.run()`、`handle-item` は `handle_item()`、いずれも `workdir=/workspace`）、`--help` で両サブコマンドが表示されることを確認する
- [ ] 2.3 ワーカーに SIGINT / SIGTERM をタスクのキャンセルへ配線し（プロセス kill ではない）、`docker stop` で強制 kill を待たずに終了することを確認する（self-hosted-environment: 停止シグナルで正常終了する）
- [ ] 2.4 イメージに BigQuery クライアントライブラリを含め、クエリスクリプトは一切同梱されていないことを `docker run --rm <image> ls /workspace` と `find / -name '*bigquery*verify*'` 相当の確認で検証する（bigquery-access-verification: 事前に用意したクエリスクリプトに依存しない）

## 3. プロビジョニング

- [ ] 3.1 `scripts/provision.py` に self-hosted Environment の作成・再利用を実装し、作成後に `config.type` が `self_hosted` であることを API レスポンスで確認する（self-hosted-environment: 環境が self-hosted である）
- [ ] 3.2 検証用カスタムスキル `skills/container-probe/SKILL.md` を作成する（呼ばれたら決まった形式でコンテナのマーカー・ホスト名・作業ディレクトリを報告する手順を書く）。スキル読み込みの有無が出力形式で判別できることをレビューで確認する
- [ ] 3.3 `provision.py` にスキルのアップロードと Agent への添付、および再実行時の新バージョン作成を実装し、2 回実行してスキルが重複作成されずバージョンが増えることを API の一覧で確認する（agent-provisioning: ローカルのスキルがアップロードされる / スキル内容の更新が新バージョンになる）
- [ ] 3.4 `mcp.json` を作成し（GitHub hosted MCP を URL 形式で宣言）、`provision.py` にその読み込みと `mcp_servers` + `mcp_toolset` への変換を実装する。`type` が `url` でない宣言や `command` を持つ宣言を与えると Agent を更新せずエラー終了することをテストで確認する（agent-provisioning: URL 形式でないサーバ宣言は拒否される）
- [ ] 3.5 `provision.py` に vault と MCP credential（まず `static_bearer` で PAT）の作成・再利用を実装し、API レスポンスにトークン値が含まれないことを確認する（agent-provisioning: 認証情報が vault に登録される）
- [ ] 3.6 `provision.py` に Agent の作成・更新を実装する（`model: claude-opus-5`、`agent_toolset_20260401` で `web_search` / `web_fetch` を `enabled: false`、`mcp_toolset`、`skills`）。2 回実行して Agent が 1 つのまま新バージョンが払い出されることを確認する（agent-provisioning: 再実行で重複作成されない / 使用モデルが既定で Claude Opus 5 である）
- [ ] 3.7 作成した ID を `.provisioned.json` に保存・読み出しする処理を実装し、ファイルを消すと再作成、残すと再利用になることを確認する

## 4. 検証ドライバ

- [ ] 4.1 `scripts/run_verification.py` にセッション作成（Agent 参照 + `environment_id` + `vault_ids`、`model`/`tools` はセッションに渡さない）とイベントストリーム購読を実装し、セッションが `running` に入ることをログで確認する（agent-provisioning: セッション作成時にモデルやツールを渡さない）
- [ ] 4.2 再接続処理を実装する（`events/stream` を開いた後に `events` を取得してイベント ID で重複排除）。ストリームを意図的に切断しても未解決の確認要求を取りこぼさずセッションが進むことを確認する
- [ ] 4.3 `agent.mcp_tool_use` に対する `user.tool_confirmation` の応答を実装する（`tool_use_id` はイベント ID `sevt_...`）。MCP ツール呼び出しが承認後に実行されて結果が返ることを確認する（agent-provisioning: MCP のツール呼び出しが承認を経て成立する）
- [ ] 4.4 終了判定を `session.status_idle` の `stop_reason` で行い、`requires_action` を終了と誤判定しないことをテストで確認する
- [ ] 4.5 検証シナリオのプロンプト列（マーカー読み取り / スキル列挙 / スキル実行 / MCP ツール列挙 / MCP ツール実行 / BigQuery / 作業ディレクトリへの書き込みと読み出し）を実装し、各シナリオの結果を人間が読める形でまとめて出力することを確認する
- [ ] 4.6 シナリオごとの結果出力に、判定に使った根拠（返答本文の該当箇所、ツール実行イベント）を含めることを確認する（self-hosted-environment: コンテナ固有のマーカーで実行場所が特定できる / bigquery-access-verification: クエリ結果がコンテナ由来であることが確認できる）

## 5. モード A（常駐単一コンテナ）

- [ ] 5.1 `scripts/mode_a_up.sh` でワーカーコンテナを `worker run` エントリポイント、`/workspace` に named volume、GCP キーを読み取り専用マウント、`GOOGLE_APPLICATION_CREDENTIALS` 設定、`ANTHROPIC_API_KEY` 非設定で起動し、`docker inspect` でこれらを確認する（self-hosted-environment: 組織スコープの API キーはワーカーホストに置かない / bigquery-access-verification: キーは読み取り専用である）
- [ ] 5.2 モード A で検証ドライバを 2 セッション連続実行し、両方がツール実行に成功しワーカーコンテナが起動したままであることを `docker ps` で確認する（self-hosted-environment: 常駐ワーカーが複数セッションを処理する）
- [ ] 5.3 モード A で 1 セッション目に作らせたファイルが 2 セッション目から読めることを確認し、状態が持ち越される性質として結果に記録する（self-hosted-environment: 常駐ワーカーは状態を持ち越す）

## 6. モード B（セッション毎コンテナ）とライフサイクルログ

- [ ] 6.1 `orchestrator/lifecycle_log.py` に `log_event` を実装する（JSON Lines、追記専用、即時フラッシュ、出力先は設定可能、既定は `logs/container-lifecycle.jsonl`）。全行が個別に JSON としてパースできることをユニットテストで確認する（container-lifecycle-log: 1 行 1 イベントで機械可読である / ログ出力先が設定可能である）
- [ ] 6.2 `orchestrator/main.py` に work poller（`auto_stop=False`）とセッション種別の item のみを対象とするディスパッチを実装し、セッション以外の item でコンテナを起動せず停止もしないことを確認する（self-hosted-environment: セッション以外の work item を取り違えない）
- [ ] 6.3 `docker run` の起動処理を実装する（コンテナ名 `cma-<work_id>`、必要な `ANTHROPIC_*` を値なし `-e` で引き渡し、`/workspace` はマウントせず、GCP キーは読み取り専用マウント）。`ps` の出力に秘密の値が現れないことを確認する（self-hosted-environment: 使い捨てコンテナに必要な環境変数が渡る）
- [ ] 6.4 `container_start` / `container_exit` の記録を実装し（`try`/`finally` で終了イベントを必ず書く。共通フィールド + `exit_code` / `duration_ms` / `error`）、1 セッション 2 ターンの実行でターン数分の開始・終了イベントが `work_id` とコンテナ名で対応付けて記録されることを確認する（container-lifecycle-log: 起動イベント / 終了イベント / 起動と終了が対応付けられる、self-hosted-environment: work item ごとにコンテナが起動・終了する）
- [ ] 6.5 異常系の記録を実装する（非ゼロ終了コード、存在しないイメージによる起動失敗で `container_start_failed` を記録し、オーケストレータは次のポーリングを続ける）。イメージ名を故意に壊した実行で確認する（container-lifecycle-log: コンテナが異常終了する / コンテナの起動自体に失敗する）
- [ ] 6.6 SIGTERM 時に in-flight コンテナの終了イベントを書いてから終了する処理を実装し、処理中に SIGTERM を送っても終了イベントのない起動イベントが残らないことをログで確認する（container-lifecycle-log: オーケストレータが停止しても対応が崩れない）
- [ ] 6.7 コンテナ起動の直前と終了の直後に、ワークスペースの復元・保存を後から挿入する箇所をそれぞれ 1 か所ずつ設け、その意図をコメントで明示する（この変更では永続化処理自体は実装しない）（container-lifecycle-log: 永続化フックの接続点）
- [ ] 6.8 ライフサイクルログとワーカーの標準出力に environment key と work secret の値が出ていないことを、実行後の `grep` で確認する（self-hosted-environment: 秘密情報がログに出ない / container-lifecycle-log の秘密非出力）
- [ ] 6.9 モード B で 1 ターン目に作らせたファイルが 2 ターン目に存在しないことを確認し、ワークスペース永続化が必要であるという結論の根拠として結果に記録する（self-hosted-environment: 使い捨てコンテナは状態を持ち越さない）

## 7. GCP / Terraform

- [ ] 7.1 `terraform/` に `google_service_account` と、変数（プロジェクト ID / データセット / テーブル / サービスアカウント名、既定値は `nnyn-dev` / `house_monitor` / `co2` / `test-claude-managed-agents`）を定義し、`terraform validate` が通ることを確認する（bigquery-access-verification: 対象が設定値として与えられる）
- [ ] 7.2 プロジェクトレベルの `roles/bigquery.jobUser` と、既存データセットへの `google_bigquery_dataset_iam_member` による `roles/bigquery.dataViewer` を定義し、既存データセット・テーブルが新規作成対象に含まれないことを `terraform plan` の出力で確認する（bigquery-access-verification: サービスアカウントと権限が作られる / 権限が対象テーブルに限定されている / 既存リソースを作り直さない）
- [ ] 7.3 サービスアカウントのメールアドレスを output に定義し、キーは Terraform では発行せず `gcloud iam service-accounts keys create` で人間が発行する手順を `terraform/README.md` に記載する（bigquery-access-verification: キーの取得方法が定まっている）
- [ ] 7.4 エージェントに `nnyn-dev.house_monitor.co2` の行数と直近データを調べさせ、その場で書いたスクリプトの実行で回答が得られることを確認する（bigquery-access-verification: エージェントが自力でクエリを実行する / キーがコンテナ内から読める）

## 8. README

- [ ] 8.1 構成の節を書く（責務の境界: エージェントループは Anthropic 側 / ツール実行は自前コンテナ / MCP は Anthropic 側、ディレクトリ構成一覧、モード A と B の違いと起動コマンド）（verification-guide: README の構成説明）
- [ ] 8.2 人間が事前に設定すべき内容の節を書く（Anthropic API キー、Console での environment key 発行、GitHub PAT とスコープ、GCP サービスアカウントキーの取得、Docker / Terraform / Python のバージョン要件、`/bin/bash` 等のイメージ要件、各秘密の置き場所とバージョン管理に入れないこと）（verification-guide: 人間が事前に設定すべき内容）
- [ ] 8.3 検証手順の節を書く（Terraform 適用 → プロビジョニング → モード A → モード B の順、各手順のコマンド、6 つの検証項目と手順の対応表）（verification-guide: 検証手順）
- [ ] 8.4 人間が確認すべき内容の節を書く（項目ごとに「どこを見るか」「何が見えていれば合格か」、ライフサイクルログのパスと 1 レコードの例、ターン数と起動終了イベント数の対応の確認方法）（verification-guide: 人間が確認すべき内容）
- [ ] 8.5 片付けの節を書く（Agent / Environment / vault / skill / Terraform 資源 / 発行したキーの一覧と片付け方、アーカイブが取り消せないことの注意）。スクリプトから自動でアーカイブしないことも明記する（verification-guide: 片付け方法が示されている）
- [ ] 8.6 検証用であってコンテナのセキュリティハードニングは範囲外であること、self-hosted では vault の `environment_variable` credential とリポジトリ内 `.claude/skills` の自動探索が使えないことを制約として記載する

## 9. 通し検証

- [ ] 9.1 README の手順に上から順に従って最初から最後まで通し実行し、6 つの検証項目（自前コンテナでの実行 / skills の認識 / MCP の認識 / モード A / モード B のライフサイクルイベント / BigQuery アクセス）すべてについて結果と根拠を記録する（verification-guide: 手順が順番に実行できる）
- [ ] 9.2 通し実行で判明した実測値（1 ターンあたりのコンテナ起動回数、GitHub MCP の認証方式が `static_bearer` で足りたか）を README と design.md に反映して確認する
