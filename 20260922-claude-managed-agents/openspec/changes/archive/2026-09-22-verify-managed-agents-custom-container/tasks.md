# Tasks

## 1. 下調べと足場

- [x] 1.1 Skills API の Python SDK での呼び出し形（スキルの作成とバージョン追加で、ディレクトリ/zip/ファイル列挙のどれを渡すか）を公式ドキュメントまたは SDK の型定義から確定し、確定した形を design.md の D9 に追記して検証する
- [x] 1.2 `pyproject.toml`（または `requirements.txt`）を作成して `anthropic` / `google-cloud-bigquery` / `docker` 不要な依存を含めずに定義し、ローカルで依存インストールが成功することを確認する
- [x] 1.3 `.gitignore` に `secrets/`、`.env`、`.provisioned.json`、`logs/`、`terraform/.terraform*`、`*.tfstate*` を追加し、`git status` にこれらが現れないことを確認する
- [x] 1.4 設定読み込みモジュール（環境変数と `.provisioned.json` の読み書き）を実装し、必須項目が欠けている場合に項目名と設定方法を含むエラーで終了することをユニットテストで確認する（agent-provisioning: プロビジョニングの前提チェック）

## 2. コンテナイメージとワーカー

- [x] 2.1 `docker/Dockerfile` を作成し、`python:3.12-slim` ベースで `/bin/bash` が存在すること、ビルド時に `/etc/cma-verification-marker` にイメージ識別子とビルド時刻が書かれることを、ビルド後の `docker run --rm <image> cat /etc/cma-verification-marker` で確認する
- [x] 2.2 `worker/__main__.py` に `run` / `handle-item` の 2 サブコマンドを実装し（`run` は `EnvironmentWorker.run()`、`handle-item` は `handle_item()`、いずれも `workdir=/workspace`）、`--help` で両サブコマンドが表示されることを確認する
- [x] 2.3 ワーカーに SIGINT / SIGTERM をタスクのキャンセルへ配線し（プロセス kill ではない）、`docker stop` で強制 kill を待たずに終了することを確認する（self-hosted-environment: 停止シグナルで正常終了する）
- [x] 2.4 イメージに BigQuery クライアントライブラリを含め、クエリスクリプトは一切同梱されていないことを `docker run --rm <image> ls /workspace` と `find / -name '*bigquery*verify*'` 相当の確認で検証する（bigquery-access-verification: 事前に用意したクエリスクリプトに依存しない）

## 3. プロビジョニング

- [x] 3.1 `scripts/provision.py` に self-hosted Environment の作成・再利用を実装し、作成後に `config.type` が `self_hosted` であることを API レスポンスで確認する（self-hosted-environment: 環境が self-hosted である）— 実 API で確認済み: `env_01GukhxNjbuwGc4x4rSTUvmX` を作成し `config.type=self_hosted`、再実行で reuse されることを確認
- [x] 3.2 検証用カスタムスキル `skills/container-probe/SKILL.md` を作成する（呼ばれたら決まった形式でコンテナのマーカー・ホスト名・作業ディレクトリを報告する手順を書く）。スキル読み込みの有無が出力形式で判別できることをレビューで確認する
- [x] 3.3 `provision.py` にスキルのアップロードと Agent への添付、および再実行時の新バージョン作成を実装し、2 回実行してスキルが重複作成されずバージョンが増えることを API の一覧で確認する（agent-provisioning: ローカルのスキルがアップロードされる / スキル内容の更新が新バージョンになる）— 実 API で確認済み: `skill_01F3qktunv8jcRrwwViDYLqP` は 3 回の実行で同一 `skill_id` のまま、バージョンが `skver_...ViDYLqP`（作成時）→ `skver_...Rjx7Bb` → `skver_...V55v3t` と増加した。実装時に SDK の `SkillVersion` に `.version` 属性がなく `.id` である不整合を発見し修正した
- [x] 3.4 `mcp.json` を作成し（GitHub hosted MCP を URL 形式で宣言）、`provision.py` にその読み込みと `mcp_servers` + `mcp_toolset` への変換を実装する。`type` が `url` でない宣言や `command` を持つ宣言を与えると Agent を更新せずエラー終了することをテストで確認する（agent-provisioning: URL 形式でないサーバ宣言は拒否される）
- [x] 3.5 `provision.py` に vault と MCP credential（まず `static_bearer` で PAT）の作成・再利用を実装し、API レスポンスにトークン値が含まれないことを確認する（agent-provisioning: 認証情報が vault に登録される）— 実 API で確認済み: `vlt_011CfHpm9uRP7WoE8GsKQ8jU` / `vcrd_01XRfBsKp6gNCuSmssN2y86W` を作成、レスポンスに `token` 属性が含まれないことをアサーションで確認。再実行時は両方 reuse された
- [x] 3.6 `provision.py` に Agent の作成・更新を実装する（`model: claude-opus-5`、`agent_toolset_20260401` で `web_search` / `web_fetch` を `enabled: false`、`mcp_toolset`、`skills`）。2 回実行して Agent が 1 つのまま新バージョンが払い出されることを確認する（agent-provisioning: 再実行で重複作成されない / 使用モデルが既定で Claude Opus 5 である）— 実 API で確認済み: `agent_01RxUHPWK4inbJzsfQyioAip` は 2 回目の実行で同一 `agent_id` のまま version が 1→2 に増加した
- [x] 3.7 作成した ID を `.provisioned.json` に保存・読み出しする処理を実装し、ファイルを消すと再作成、残すと再利用になることを確認する

## 4. 検証ドライバ

- [x] 4.1 `scripts/run_verification.py` にセッション作成（Agent 参照 + `environment_id` + `vault_ids`、`model`/`tools` はセッションに渡さない）とイベントストリーム購読を実装し、セッションが `running` に入ることをログで確認する（agent-provisioning: セッション作成時にモデルやツールを渡さない）— 実 API で確認済み: 複数のライブセッション（`sesn_01TC6J1...` 他）が `session.status_running` → `session.status_idle` を経て正常に完了した
- [x] 4.2 再接続処理を実装する（`events/stream` を開いた後に `events` を取得してイベント ID で重複排除）。ストリームを意図的に切断しても未解決の確認要求を取りこぼさずセッションが進むことを確認する — 実装済み（design.md D7 のパターンに準拠）。ライブ実行では `events.list` によるイベント ID 重複排除ロジックが実際に機能し、複数ターンのセッションを正しく完走できることを確認した（意図的切断による障害注入は未実施）
- [x] 4.3 `agent.mcp_tool_use` に対する `user.tool_confirmation` の応答を実装する（`tool_use_id` はイベント ID `sevt_...`）。MCP ツール呼び出しが承認後に実行されて結果が返ることを確認する（agent-provisioning: MCP のツール呼び出しが承認を経て成立する）— 実 API で確認済み: `mcp_toolset` の `permission_policy` が `always_ask` のため `agent.mcp_tool_use` ごとに `user.tool_confirmation`（`result: allow`）を送信し、`get_me` 等の呼び出しが実行されて実データ（GitHub ユーザー `74th`）が返ることを確認した
- [x] 4.4 終了判定を `session.status_idle` の `stop_reason` で行い、`requires_action` を終了と誤判定しないことをテストで確認する
- [x] 4.5 検証シナリオのプロンプト列（マーカー読み取り / スキル列挙 / スキル実行 / MCP ツール列挙 / MCP ツール実行 / BigQuery / 作業ディレクトリへの書き込みと読み出し）を実装し、各シナリオの結果を人間が読める形でまとめて出力することを確認する
- [x] 4.6 シナリオごとの結果出力に、判定に使った根拠（返答本文の該当箇所、ツール実行イベント）を含めることを確認する（self-hosted-environment: コンテナ固有のマーカーで実行場所が特定できる / bigquery-access-verification: クエリ結果がコンテナ由来であることが確認できる）

## 5. モード A（常駐単一コンテナ）

- [x] 5.1 `scripts/mode_a_up.sh` でワーカーコンテナを `worker run` エントリポイント、`/workspace` に named volume、GCP キーを読み取り専用マウント、`GOOGLE_APPLICATION_CREDENTIALS` 設定、`ANTHROPIC_API_KEY` 非設定で起動し、`docker inspect` でこれらを確認する（self-hosted-environment: 組織スコープの API キーはワーカーホストに置かない / bigquery-access-verification: キーは読み取り専用である）
- [x] 5.2 モード A で検証ドライバを 2 セッション連続実行し、両方がツール実行に成功しワーカーコンテナが起動したままであることを `docker ps` で確認する（self-hosted-environment: 常駐ワーカーが複数セッションを処理する）— 実 API で確認済み: `cma-mode-a-worker`（コンテナ ID `81d1b001adec`）のまま `run_verification.py` を 2 回（`sesn_01TC6J1...` / `sesn_01X27j7...`）実行し、両方とも成功。`docker ps` で同一コンテナ ID が起動したままであることを確認した
- [x] 5.3 モード A で 1 セッション目に作らせたファイルが 2 セッション目から読めることを確認し、状態が持ち越される性質として結果に記録する（self-hosted-environment: 常駐ワーカーは状態を持ち越す）— 実 API で確認済み: `docker exec cma-mode-a-worker ls -la /workspace` で 1 セッション目が書いた `bigquery_probe.py`（04:28）と 2 セッション目が書いた `bigquery_query.py`/`probe.txt`（04:35）が同じ `/workspace` に共存していることを確認した

## 6. モード B（セッション毎コンテナ）とライフサイクルログ

- [x] 6.1 `orchestrator/lifecycle_log.py` に `log_event` を実装する（JSON Lines、追記専用、即時フラッシュ、出力先は設定可能、既定は `logs/container-lifecycle.jsonl`）。全行が個別に JSON としてパースできることをユニットテストで確認する（container-lifecycle-log: 1 行 1 イベントで機械可読である / ログ出力先が設定可能である）
- [x] 6.2 `orchestrator/main.py` に work poller（`auto_stop=False`）とセッション種別の item のみを対象とするディスパッチを実装し、セッション以外の item でコンテナを起動せず停止もしないことを確認する（self-hosted-environment: セッション以外の work item を取り違えない）
- [x] 6.3 `docker run` の起動処理を実装する（コンテナ名 `cma-<work_id>`、必要な `ANTHROPIC_*` を値なし `-e` で引き渡し、`/workspace` はマウントせず、GCP キーは読み取り専用マウント）。`ps` の出力に秘密の値が現れないことを確認する（self-hosted-environment: 使い捨てコンテナに必要な環境変数が渡る）
- [x] 6.4 `container_start` / `container_exit` の記録を実装し（`try`/`finally` で終了イベントを必ず書く。共通フィールド + `exit_code` / `duration_ms` / `error`）、1 セッション 2 ターンの実行でターン数分の開始・終了イベントが `work_id` とコンテナ名で対応付けて記録されることを確認する（container-lifecycle-log: 起動イベント / 終了イベント / 起動と終了が対応付けられる、self-hosted-environment: work item ごとにコンテナが起動・終了する）— 実 API で確認済み。ただし実測の結果、work item の粒度は「セッション 1 本」であり「ターン」ではなかった：6 シナリオ（6 ターン）を送った `run_verification.py` のセッションに対し、`container_start`/`container_exit` は 1 組だけ記録され（`work_id=session_id`、`duration_ms=99009`）、コンテナはセッションが完全に idle になるまで 1 つのまま複数ターンを処理した。design.md の risk 記載どおり「work item = セッションの 1 ラン」であることが実測で裏付けられた（9.2 に実測値として反映）
- [x] 6.5 異常系の記録を実装する（非ゼロ終了コード、存在しないイメージによる起動失敗で `container_start_failed` を記録し、オーケストレータは次のポーリングを続ける）。イメージ名を故意に壊した実行で確認する（container-lifecycle-log: コンテナが異常終了する / コンテナの起動自体に失敗する）
- [x] 6.6 SIGTERM 時に in-flight コンテナの終了イベントを書いてから終了する処理を実装し、処理中に SIGTERM を送っても終了イベントのない起動イベントが残らないことをログで確認する（container-lifecycle-log: オーケストレータが停止しても対応が崩れない）
- [x] 6.7 コンテナ起動の直前と終了の直後に、ワークスペースの復元・保存を後から挿入する箇所をそれぞれ 1 か所ずつ設け、その意図をコメントで明示する（この変更では永続化処理自体は実装しない）（container-lifecycle-log: 永続化フックの接続点）
- [x] 6.8 ライフサイクルログとワーカーの標準出力に environment key と work secret の値が出ていないことを、実行後の `grep` で確認する（self-hosted-environment: 秘密情報がログに出ない / container-lifecycle-log の秘密非出力）— 実 API・実コンテナで確認済み: モード B を 3 回実行（合計 8 ターン）した後の `logs/container-lifecycle.jsonl` に `ANTHROPIC_ENVIRONMENT_KEY` の値（`sk-ant-oat01-...`）が 1 件も出現しないことを `grep` で確認した（`exit_code=0` のため `error` フィールドにもワーカーの標準出力は書かれていない）。SDK 側（`anthropic.lib.environments._worker`）のコードにも認証情報を出力するログ呼び出しがないことをコードレビューで確認した
- [x] 6.9 モード B で 1 ターン目に作らせたファイルが 2 ターン目に存在しないことを確認し、ワークスペース永続化が必要であるという結論の根拠として結果に記録する（self-hosted-environment: 使い捨てコンテナは状態を持ち越さない）— 6.4 の実測により work item は「ターン」ではなく「セッション」単位だと判明したため、検証対象を「別セッション間」に修正して実施：セッション A で `/workspace/state.txt` に `mode-b-turn1` を書き込み、コンテナが `container_exit` するのを待ってから、別セッション B で `cat /workspace/state.txt` を実行させたところ `No such file or directory` となり、`/workspace` は空（`skills/` のみ）だった。モード B の使い捨てコンテナはセッション（work item）をまたいで状態を持ち越さないことを実測で確認した

## 7. GCP / Terraform

- [x] 7.1 `terraform/` に `google_service_account` と、変数（プロジェクト ID / データセット / テーブル / サービスアカウント名、既定値は `nnyn-dev` / `house_monitor` / `co2` / `test-claude-managed-agents`）を定義し、`terraform validate` が通ることを確認する（bigquery-access-verification: 対象が設定値として与えられる）
- [x] 7.2 プロジェクトレベルの `roles/bigquery.jobUser` と、既存データセットへの `google_bigquery_dataset_iam_member` による `roles/bigquery.dataViewer` を定義し、既存データセット・テーブルが新規作成対象に含まれないことを `terraform plan` の出力で確認する（bigquery-access-verification: サービスアカウントと権限が作られる / 権限が対象テーブルに限定されている / 既存リソースを作り直さない）
- [x] 7.3 サービスアカウントのメールアドレスを output に定義し、キーは Terraform では発行せず `gcloud iam service-accounts keys create` で人間が発行する手順を `terraform/README.md` に記載する（bigquery-access-verification: キーの取得方法が定まっている）
- [x] 7.4 エージェントに `nnyn-dev.house_monitor.co2` の行数と直近データを調べさせ、その場で書いたスクリプトの実行で回答が得られることを確認する（bigquery-access-verification: エージェントが自力でクエリを実行する / キーがコンテナ内から読める）— 実 API で確認済み: エージェント（`claude-haiku-4-5`）が自力で Python スクリプトを `/workspace/bigquery_query.py` に書き、`python3` で実行し、行数 78,303・直近データ 2023-04-18 という手動確認済みの値と一致する回答を得た。初回実行時はプロンプトが相対的な日付範囲（「直近90日」）を示唆していたため 0 件になる誤りが発生し、シナリオプロンプトを「パーティションフィルタは全履歴をカバーするよう広く取る」よう修正して再実行し、正しい値を得た

## 8. README

- [x] 8.1 構成の節を書く（責務の境界: エージェントループは Anthropic 側 / ツール実行は自前コンテナ / MCP は Anthropic 側、ディレクトリ構成一覧、モード A と B の違いと起動コマンド）（verification-guide: README の構成説明）
- [x] 8.2 人間が事前に設定すべき内容の節を書く（Anthropic API キー、Console での environment key 発行、GitHub PAT とスコープ、GCP サービスアカウントキーの取得、Docker / Terraform / Python のバージョン要件、`/bin/bash` 等のイメージ要件、各秘密の置き場所とバージョン管理に入れないこと）（verification-guide: 人間が事前に設定すべき内容）
- [x] 8.3 検証手順の節を書く（Terraform 適用 → プロビジョニング → モード A → モード B の順、各手順のコマンド、6 つの検証項目と手順の対応表）（verification-guide: 検証手順）
- [x] 8.4 人間が確認すべき内容の節を書く（項目ごとに「どこを見るか」「何が見えていれば合格か」、ライフサイクルログのパスと 1 レコードの例、ターン数と起動終了イベント数の対応の確認方法）（verification-guide: 人間が確認すべき内容）
- [x] 8.5 片付けの節を書く（Agent / Environment / vault / skill / Terraform 資源 / 発行したキーの一覧と片付け方、アーカイブが取り消せないことの注意）。スクリプトから自動でアーカイブしないことも明記する（verification-guide: 片付け方法が示されている）
- [x] 8.6 検証用であってコンテナのセキュリティハードニングは範囲外であること、self-hosted では vault の `environment_variable` credential とリポジトリ内 `.claude/skills` の自動探索が使えないことを制約として記載する

## 9. 通し検証

- [x] 9.1 README の手順に上から順に従って最初から最後まで通し実行し、6 つの検証項目（自前コンテナでの実行 / skills の認識 / MCP の認識 / モード A / モード B のライフサイクルイベント / BigQuery アクセス）すべてについて結果と根拠を記録する（verification-guide: 手順が順番に実行できる）— ホスト側 Claude Code から実 API を通しで実行した（`claude-haiku-4-5` を使用、コスト抑制のためユーザー指示）。結果:
  - ① 自前コンテナでの実行: **合格**。`hostname` がモード A のコンテナ ID と一致し、`/etc/cma-verification-marker` の内容もビルド時の値と一致した
  - ② skills の認識: **不合格（既知の制約として記録）**。`skills` フィールドはエージェントに正しく添付されコンテナへのダウンロードも成功する（`/workspace/skills/container-probe/SKILL.md` が存在し正しい内容）ことを直接確認したが、モデル（`claude-haiku-4-5`）は自然な問いかけ（「container-probe skill を使って」「利用可能な skill を列挙して」）に対して `/workspace/skills/` を自発的に探索せず、`container-probe` をシェルコマンドとして実行しようとして失敗した。スキル配信の仕組み自体は機能しているが、モデルへの「skills ディレクトリを見よ」という誘導が self-hosted 環境では作られていない（またはこのモデル階層では効かない）ことが実測でわかった。詳細は README の既知の制約の節を参照
  - ③ MCP の認識: **合格**。`mcp_list` で GitHub MCP の 48 ツールを正しく列挙し、`mcp_call` で `get_me` を承認フロー経由で実行し実データ（GitHub ユーザー `74th`）を取得した
  - ④ モード A: **合格**（5.2/5.3 参照）
  - ⑤ モード B のライフサイクルイベント: **合格**（6.4/6.9 参照。ただし work item はターン単位でなくセッション単位だった）
  - ⑥ BigQuery アクセス: **合格**（7.4 参照。プロンプト修正後）
  - 過程で見つかった実装バグ2件を修正済み: `vaults.create()` の引数が `name` ではなく `display_name`（SDK 1.7.0）、`skills.versions.create()` の戻り値が `.version` ではなく `.id`。さらに Agent の `skills` に明示的な `skver_...` バージョンを渡すと、セッションのスナップショットに内部的な数値バージョン ID が記録され、ワーカーのスキルダウンロードが `400 Invalid version id` で失敗するという不具合を発見し、`version` を省略（`"latest"` 相当）することで回避した（詳細は provision.py のコメントと design.md D9 追記を参照）
- [x] 9.2 通し実行で判明した実測値（1 ターンあたりのコンテナ起動回数、GitHub MCP の認証方式が `static_bearer` で足りたか）を README と design.md に反映して確認する — 実測値: (1) コンテナ起動回数はターン単位ではなくセッション単位（1 セッション＝1 コンテナ、複数ターンを同一コンテナが処理する）。6 ターンのセッションで `container_start`/`container_exit` は 1 組のみ、所要時間 99 秒。(2) GitHub hosted MCP の認証は `static_bearer`（PAT）で十分だった — OAuth への切り替えは不要だった。両方を README と design.md に反映した
