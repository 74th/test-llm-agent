# Tasks

## 1. 人間のセットアップ（claude.ai / GitHub 側、自動化不可）

- [x] 1.1 Owner ロールで [Cloud environments](https://claude.ai/admin-settings/cloud-environments) の **Allow self-hosted environments** を有効にし、**New** ボタンが表示されることを確認する
- [x] 1.2 environment を作成し、**Copy environment key** で environment secret を取得して `container/.env` 相当の安全な場所（git 管理外）に保存する。あわせて `ccpool_...` 形式の environment ID を控える。key は一度しか表示されない
- [x] 1.3 組織の GitHub 連携が有効で、セッション開始時にリポジトリを選択できることを確認する
- [x] 1.4 GitHub MCP 用の PAT を発行し（検証に必要な最小スコープ）、git 管理外に保存する
- [x] 1.5 検証に使うリポジトリを 1 つ決める（design.md の Open Question）。決めた名前を `README.md` に記録する
- [x] 1.6 ホスト側の時刻が NTP で同期していること（ずれ 5 分未満）と Docker が使えることを確認する
- [x] 1.7 `nnyn-dev` に対する terraform apply 権限があることと、BigQuery テーブル `nnyn-dev.house_monitor.co2` が存在することを確認する
- [x] 1.8 セクション 2 の terraform apply 後、`gcloud iam service-accounts keys create` でサービスアカウントキーを発行し、git 管理外のパスに 0600 で保存する。キーは terraform では作らない（tfstate に平文で残るため）

## 2. Terraform（GCP サービスアカウント）

- [x] 2.1 `terraform/` に provider と variables を作る。プロジェクトは `nnyn-dev`、データセット `house_monitor`、テーブル `co2` を変数化する。`terraform init` が成功することで確認
- [x] 2.2 サービスアカウントを定義する。`account_id = "test-claude-self-hosted-env"`（30 文字上限のため短縮）、`display_name = "test-claude-self-hosted-environment"`。`terraform plan` に SA の作成が現れることで確認
- [x] 2.3 プロジェクトレベルで `roles/bigquery.jobUser` を付与する（クエリ実行）。データセット全体やプロジェクト全体の dataViewer は付けない
- [x] 2.4 テーブルレベルで `google_bigquery_table_iam_member` により `roles/bigquery.dataViewer` を付与する。テーブルは `data` 参照とし、`terraform plan` にテーブル自体の作成・変更・削除が現れないことを確認
- [x] 2.5 `outputs.tf` で SA のメールアドレスのみを出力する。キーやシークレットを出力しないことを確認
- [x] 2.6 `terraform apply` を実行し、発行したキーで `bq query` により `nnyn-dev.house_monitor.co2` を引けることをホスト側から確認する
- [x] 2.7 同じキーで同一データセット内の別テーブル、または別データセットのテーブルを引き、権限エラーで拒否されることを確認する

## 3. コンテナイメージ

- [x] 3.1 `container/Dockerfile` を作成する。Debian bookworm-slim + `git curl ca-certificates openssh-client jq`、`ARG CLAUDE_CODE_VERSION` で `downloads.claude.ai` から `claude` バイナリを取得、system スコープで `user.name` / `user.email` / `safe.directory '*'` を設定、`HOME=/opt/claude-config` を設定。`docker build --build-arg CLAUDE_CODE_VERSION=<version>` が成功することで確認
- [x] 3.2 ビルドしたイメージで `claude self-hosted-runner --help` を実行し、`--environment-secret-file` が usage に現れることを確認する
- [x] 3.3 同イメージで `git --version` が 2.34 以降であることと `git config --system --get user.email` が空でないことを確認する
- [x] 3.4 Dockerfile に `google-cloud-sdk`（`bq` / `gcloud`）を追加する。`docker run --rm <image> bq version` が成功することで確認
- [x] 3.5 `docker history` とイメージ内の grep で、environment secret / GitHub PAT / サービスアカウントキーの値がレイヤに含まれないことを確認する

## 4. entrypoint と設定の seed

- [x] 4.1 `container/entrypoint.sh` を作成する。`/mnt/workspace` から `/opt/claude-config/` へコピーし、`GITHUB_PAT` から `mcpServers.github`（type `http`、url `https://api.githubcopilot.com/mcp/`、`Authorization: Bearer` ヘッダ）を含む `.claude.json` を `/opt/claude-config/.claude.json` と `/opt/claude-config/.claude/.claude.json` の両方に書き出し、第 1 引数 `runner` / `orchestrator` で起動先を切り替える。`GITHUB_PAT` 未設定なら変数名を stderr に出して非ゼロ終了する
- [x] 4.2 `GITHUB_PAT` を与えずにコンテナを起動し、変数名を含むエラーで非ゼロ終了することを確認する
- [x] 4.3 `GITHUB_PAT` を与えて起動し、`/opt/claude-config/.claude.json` と `/opt/claude-config/.claude/.claude.json` の両方が生成され、`.claude/skills/what-is-pentelpantel/SKILL.md` がコピーされていることを確認する
- [x] 4.4 ホスト側で `git status` を実行し、生成された設定ファイルが作業ツリーに現れないことを確認する
- [x] 4.5 `container/session-wrapper.sh` を作成する。`exec "$CLAUDE_RUNNER_CLAUDE_BIN" "$@" --permission-mode auto` のみ。実行ビットが立っていることを確認する

## 5. 常駐モード（モード A）

- [x] 5.1 `container/compose.persistent.yaml` を作成する。`workspace/` を `/mnt/workspace:ro`、サービスアカウントキーを `/run/secrets/gcp-sa.json:ro`、イベントログを `/var/log/ccr-events:rw` でマウントし、`GOOGLE_APPLICATION_CREDENTIALS` をそのパスに設定、environment secret を secret ファイルで渡し、`self-hosted-runner --capacity 1 --base-dir /var/lib/claude-runner --use-anthropic-git-proxy --drain-grace-sec 3600 --exec-path /opt/claude/session-wrapper.sh --log-level debug` を起動、`restart: always`、`stop_grace_period: 90s`
- [x] 5.2 `container/.env.example` を作成し、人間が埋める変数（environment secret ファイルのパス、`GITHUB_PAT`、`CLAUDE_CODE_VERSION`、サービスアカウントキーのホスト側パス）を列挙する。実値ファイルとキーは `.gitignore` に入れる
- [x] 5.3 起動したコンテナ内で `GOOGLE_APPLICATION_CREDENTIALS` の指すファイルが読めること、`/opt/claude-config` 配下にキーがコピーされていないことを確認する
- [x] 5.4 起動して runner のログに登録成功が出ること、claude.ai の Cloud environments で当該 environment が **Healthy** になることを確認する
- [x] 5.5 runner の起動ログ（debug）から、host config スナップショットと MCP 設定がどのパスから読まれたかを読み取り、`.claude.json` が「隣」と「中」のどちらで認識されたかを `README.md` に記録する

## 6. セッション毎モード（モード B）

- [x] 6.1 `container/hooks/spawn-runner` を作成する（実行可能）。`CLAUDE_RUNNER_WORK_ORDER_FILE` の中身を読み、内部契約（stdin に JWT、env に `SPAWN_ORDER_ID` / `SPAWN_RUNNER_IMAGE` / `SPAWN_RUNNER_ARGS` / `SPAWN_RUNNER_MOUNTS` / `SPAWN_SESSION_ID`）へ正規化して `RUNNER_SPAWN_BACKEND` を `exec` する。`CLAUDE_RUNNER_SESSION_ID` は `${VAR:-}` で参照する。バックエンドの終了コードを変換しないことを、終了コードを固定したダミーバックエンドで確認
- [x] 6.2 `container/provisioners/docker.sh` を作成する（実行可能）。stdin から JWT を読み、`umask 077` の一時 env ファイル経由で `docker run -d --rm --name ccr-$SPAWN_ORDER_ID` を `--capacity 1` で起動し、一時ファイルを削除する。`SPAWN_RUNNER_MOUNTS` を `-v` へ変換する。同名コンテナが既にあれば exit 0。`CLAUDE_RUNNER_` で始まる変数を参照していないことを grep で確認
- [x] 6.3 `container/provisioners/gke.sh.example` を置く。内部契約のコメントと、`SPAWN_ORDER_ID` 由来の名前で Job と Secret を `kubectl apply` する骨子、`SPAWN_RUNNER_MOUNTS` を Volume + Secret へ変換する箇所のメモを書く。今回は実装しない
- [x] 6.4 `container/compose.ondemand.yaml` を作成する。orchestrator コンテナに environment secret・`/var/run/docker.sock`・`container/hooks` と `container/provisioners`・イベントログディレクトリをマウントし、`RUNNER_SPAWN_BACKEND` を `docker.sh` に向けて `self-hosted-runner orchestrator --hooks-dir ... --expected-spawn-seconds <p99>` を起動する
- [x] 6.5 orchestrator を起動し、`/healthz` が応答することと、モード A のコンテナが停止していることを確認する
- [x] 6.6 同じ `SPAWN_ORDER_ID` で `spawn-runner` を手動で 2 回実行し、起動するコンテナが 1 つだけで、2 回目も exit 0 になることを確認する
- [x] 6.7 `docker.sh` を意図的に失敗させ、stderr に原因が出て work-order JWT と GitHub トークンの値が含まれないことを確認する
- [x] 6.8 起動されたセッションコンテナの環境変数とマウントを `docker inspect` で確認し、environment secret が渡っておらず work-order JWT のみであること、サービスアカウントキーがモード A と同じパスに読み取り専用で付いていることを確認する

## 7. ライフサイクルイベントのログ（永続化は実装しない）

- [x] 7.1 `container/log-event.sh` を作成する。共通フィールド（`ts` / `event` / `session_id`）と追加のキーバリューを受け取り、`/var/log/ccr-events/events.jsonl` へ 1 行 1 JSON で追記する。同時書き込みで行が壊れないよう追記は 1 回の write にまとめる。2 プロセスから同時に呼んでも全行が JSON として解析できることで確認
- [x] 7.2 `log-event.sh` が秘密情報を出さないことを担保する。work-order JWT・`CLAUDE_CODE_SESSION_ACCESS_TOKEN`・`GITHUB_PAT`・SA キーの値を渡しても出力に現れないことを確認
- [x] 7.3 ホスト側のログディレクトリを両モードで `/var/log/ccr-events` に **rw** でマウントする。モード A は compose、モード B は `SPAWN_RUNNER_MOUNTS` 経由。`SPAWN_RUNNER_MOUNTS` の記法を `<source>:<container-path>:<ro|rw>` に拡張し、`docker.sh` が `rw` を正しく変換することを確認
- [x] 7.4 `container/hooks/post-session` を作成する（実行可能）。`CLAUDE_RUNNER_EXIT_REASON`、`CLAUDE_RUNNER_WORKSPACE_PATHS` の各パスの存在有無・ファイル数・`git status --porcelain` の行数、フック自身の所要ミリ秒をログに残す。**ワークスペースの保存は行わない**
- [x] 7.5 `container/hooks/spawn-runner` と `container/session-wrapper.sh` に `log-event.sh` の呼び出しを足す。wrapper は `exec` の前に呼び、stdin と fd 3 を壊さないことを確認
- [x] 7.6 `workspace/.claude/settings.json` に `SessionStart` / `PostToolUse` / `Stop` / `SessionEnd` のフックを定義し、いずれも `log-event.sh` を呼ぶようにする。セッション内で複数回ツールを実行させ、回数に応じた `PostToolUse` イベントが記録されることで確認
- [x] 7.7 `container/checkout-probe/checkout` を作成する（実行可能）。公開リポジトリを自前で `git clone` して `CLAUDE_RUNNER_CHECKOUT_PATH` に置き、呼ばれたことをログに残す。本編の 2 モードには常設せず、単発検証専用とする（`--use-anthropic-git-proxy` と両立しないため）
- [ ] 7.8 イベントログのフックを有効・無効で同じセッションを実行し、セッションの結果が変わらないことを確認する
- [ ] 7.9 未コミットの変更を残したままセッションを終了させ、その変更がどこにも保存されていないこと（永続化未実装）とログに「保存可能だった」記録が残ることを確認する

## 8. README

- [x] 8.1 リポジトリ直下に `README.md` を作成し、「構成」「人間が設定すべき内容」「検証手順」「人間が検証すべき内容」の 4 セクションを置く。他の文書を参照せずに検証を通せることで確認
- [x] 8.2 **構成** セクションを書く。`container/` と `workspace/` と `terraform/` のファイル一覧と各役割、コンテナ内のマウント先（`/mnt/workspace:ro` → `/opt/claude-config`）、`--base-dir` が `/var/lib/claude-runner` である理由、2 モードの違いを図または表で示す
- [x] 8.3 **構成** セクションにイベントログの設計を書く。runner レベルとセッション内の 2 つのイベント面、それぞれで取れるイベントと参照できる情報、ログの置き場と JSONL のフィールド。`--exec-path` を使うと `command` フックが無視される排他関係、`checkout` フックが組み込みのクローンを置き換えるため本編に常設できないことも書く。**永続化は未実装**であることを明記する
- [x] 8.4 **構成** セクションに spawn の 2 層構造を書く。`hooks/spawn-runner` と `provisioners/*.sh` の責務分担、内部契約の表（stdin の JWT と `SPAWN_*` 変数）、プロビジョナが守る 3 規約（冪等キー・リトライしない・終了コード）、GKE へ移行するとき何を書けばよいか
- [x] 8.5 **人間が設定すべき内容** セクションを書く。セクション 1 の項目を必要ロール付きのチェックリストにし、GitHub PAT の発行手順と必要スコープ、environment key の取得手順、`terraform apply` の実行と `gcloud iam service-accounts keys create` によるキー発行手順を含める。それぞれの保存先（git 管理外のどのファイル）とコンテナへの渡し方（secret ファイル / 環境変数 / 読み取り専用マウント）を明記する。キーを terraform で作らない理由（tfstate に平文で残る）も書く
- [x] 8.6 **検証手順** セクションを書く。モード A とモード B それぞれについて、ビルド → 起動 → 確認 → 停止・片付けまでのコマンド列を、コピーして実行できる形で並べる。どの手順がコマンドで済み、どの手順が claude.ai の画面操作かを各手順に明示する
- [x] 8.7 **人間が検証すべき内容** セクションを書く。claude.ai のセッションへ貼り付ける 5 プロンプト — (a) 利用可能な skill の列挙、(b) 「ペンテルパンテルとは何か」、(c) 利用可能な MCP ツールの列挙、(d) GitHub MCP 経由でのリポジトリ情報取得、(e) `nnyn-dev.house_monitor.co2` にアクセスするスクリプトをその場で書いて実行し行数を答えさせる — をコピー可能な形で載せ、各プロンプトに「応答がこうなっていれば合格」の判定条件を併記する。(e) は既製スクリプトを渡さず Claude に書かせること、およびそれが実行場所の証明になる理由も書く
- [x] 8.8 モード × 確認項目のマトリクス表（成功 / 失敗 / 未実施）を README に用意する
- [x] 8.9 切り分け手順を書く。`--log-level debug` での起動ログ確認、host config の向き先の確認方法、認識されなかった MCP エントリに対する runner の警告の読み方、BigQuery アクセス失敗時に「資格情報が届いていない / 権限不足 / egress 遮断」を見分ける方法
- [x] 8.10 検証用途限定である旨（auto モード固定、Docker ソケットマウント、default-deny egress 未適用、ワークスペース共有）を README に注記する
- [x] 8.11 片付け手順を書く。コンテナとイメージの削除、claude.ai の environment 削除、GitHub PAT の失効、サービスアカウントキーの失効、`terraform destroy`

## 9. 実機検証

- [x] 9.1 モード A で claude.ai からセッションを開始し、8.7 の 5 プロンプトを実行して結果をマトリクスに記録する
- [ ] 9.2 モード A で 2 回目のセッションを投げ、同一コンテナのログに 2 回目の `Picked up session` が出ることを確認する
- [ ] 9.3 runner 起動中に `workspace/.claude/skills/` へ新しい skill を追加し、新セッションから見えないこと、`docker compose restart` 後の新セッションから見えることを確認して記録する
- [x] 9.4 モード B に切り替えて 8.7 の 5 プロンプトを実行し、結果をマトリクスに記録する
- [ ] 9.5 モード B で 2 セッションを連続実行し、`docker events` または `docker ps -a` から別々のコンテナが起動・破棄されたことを確認する
- [ ] 9.6 両モードでイベントログを収集し、1 セッションの流れ（起動要求 → セッション開始 → セッション内イベント → セッション終了）がセッション識別子で時系列に追えることを確認する
- [ ] 9.7 終了理由を 3 通り起こしてログに記録されることを確認する。正常終了、セッションを異常終了させる、アイドル解放または runner のドレインによる中断
- [ ] 9.8 アイドル解放とプロンプト待ち解放の両方を起こし、`post-session` と解放の前後関係がドキュメントの記述どおりかをログの順序で確認して記録する
- [ ] 9.9 `post-session` の所要時間をログから読み、既定の 60 秒タイムアウトに対する余裕を記録する
- [ ] 9.10 ログ全体を走査し、work-order JWT・セッショントークン・GitHub PAT・SA キーの値が含まれないことを確認する
- [ ] 9.11 `checkout-probe` を使った単発検証を行い、チェックアウト段階のフックが呼ばれてセッションが作業ツリーを得ることを確認する。本編の 2 モードには戻さない
- [ ] 9.12 プロンプト (e) について、セッションが書いたスクリプトの内容と実行結果を記録し、コンテナ内の資格情報とツールチェーンの両方が使われたことを確認する
- [ ] 9.13 検証時の Claude Code バージョンと、両モードの結果差分、および永続化の実装可否の判断（どのイベントで何が救えたはずか）を `README.md` にまとめる
