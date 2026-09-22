# Design

## Context

動機は proposal.md - Why を参照。ドキュメントを読んだ結果、設計上重要な前提は次の 4 点。

1. **セッションの作業ディレクトリは GitHub のクローンであって、マウントしたワークスペースではない。** runner はセッションごとにリポジトリを `--base-dir` 配下へチェックアウトし、そこで子プロセスを起動する。したがってマウントする `workspace/` は「プロジェクト」ではなく **user レベルの config**（`~/.claude` に相当するもの）として効かせる。
2. **skills / settings / agents / commands は runner 起動時の host config スナップショットからセッションへ seed される。** 対象は既定で `~/.claude`、`SELF_HOSTED_RUNNER_HOST_CONFIG_DIR` で差し替え可能。スナップショットは**起動時に一度だけ**取られる。
3. **MCP は `settings.json` ではなく `.claude.json` の `mcpServers` キーから seed される。** `.claude.json` は `~/.claude` の中ではなく**隣**にある。`SELF_HOSTED_RUNNER_HOST_CONFIG_DIR` を設定すると「そのディレクトリから `.claude.json` を読む」と書かれており、既定レイアウト（隣）と設定時レイアウト（中）が食い違う。
4. **runner の `--base-dir` 既定値は `/workspace`。** リポジトリ側のディレクトリ名と衝突するので、コンテナ内のマウント先とは別パスにする。

## Goals / Non-Goals

**Goals:**

- 1 つのイメージで常駐モードとセッション毎モードの両方を動かす。
- ワークスペースを差し替えるだけで skills と MCP を入れ替えられるようにする。
- シークレット（environment key / GitHub PAT）をイメージにもリポジトリにも残さない。
- `.claude.json` の探索先の曖昧さ（前提 3）に、推測で賭けずに済む構成にする。

**Non-Goals:**

- 本番ハードニング（default-deny egress、per-session の最小権限 git 資格情報、監視・メトリクス）。検証用途に限定する。
- セッションごとに新しいワークスペースを構築すること。ユーザ指示により今回は省略し、全セッションが同一ワークスペースを共有する。
- Kubernetes 上での運用。ローカル Docker のみ。

## Decisions

### D1: host config は `HOME` の差し替えで効かせ、`SELF_HOSTED_RUNNER_HOST_CONFIG_DIR` は使わない

コンテナ内に書き込み可能な config ルート `/opt/claude-config` を用意し、`HOME=/opt/claude-config` を設定する。すると `~/.claude` = `/opt/claude-config/.claude`、`~/.claude.json` = `/opt/claude-config/.claude.json` となり、**ドキュメントの既定レイアウトそのまま**になる。

- 代替案: `SELF_HOSTED_RUNNER_HOST_CONFIG_DIR=/mnt/workspace/.claude` を直接指す。却下理由は 2 つ。(a) 前提 3 の曖昧さに賭けることになる。(b) マウントを読み取り専用にできなくなる（`.claude.json` を書き込む必要があるため）。
- 保険として entrypoint は `.claude.json` を `/opt/claude-config/.claude.json`（隣）と `/opt/claude-config/.claude/.claude.json`（中）の両方に書く。余分な 1 ファイルのコストで、どちらの解釈でも MCP が届く。検証タスクで実際にどちらが読まれたかをログから確認し、結果を記録する。

### D2: ワークスペースは読み取り専用マウント + コンテナ内コピー

`workspace/` は `/mnt/workspace` に `:ro` でマウントし、entrypoint が `/opt/claude-config/` へコピーしてから生成物（`.claude.json`）を書き足す。

- リポジトリに生成物が残らない（spec: 生成物がリポジトリに残らない）。
- hooks や skill をセッション側のコードが書き換えられない（ドキュメントのハードニング指針に沿う）。
- 代替案の read-write 直マウントは、PAT を含む `.claude.json` がリポジトリ作業ツリーに落ちるので却下。

### D3: `--base-dir` は `/var/lib/claude-runner`

既定の `/workspace` を避ける（前提 4）。また環境内の全 runner で同じ値にする必要があるため、両モードで同一値を使う。

### D4: git 認証は Anthropic git proxy を使う

`--use-anthropic-git-proxy` を両モードで指定する。イメージに SSH 鍵も credential helper も `.netrc` も不要になり、セッション作成者の GitHub OAuth トークンでクローンされる。制約は `--capacity 1` と git 2.32+ で、どちらも本設計と整合する（D5）。

- 代替案: イメージに deploy key を焼く → シークレットをイメージに入れない方針に反する。
- 代替案: wrapper script で per-session に PAT を発行 → 検証には過剰。
- 前提: GitHub.com を使うこと（Anthropic 側から到達可能である必要がある）。社内 Git ホストを使う場合はこの決定を見直す。

### D5: 両モードとも `--capacity 1`

D4 が要求する。加えてセッション毎モードでは work-order が 1 runner 1 セッションに束縛されるため必然。常駐モードも揃えることで、2 モード間の差分を「コンテナのライフサイクルだけ」に絞れ、検証結果の比較が成立する。

### D6: 常駐モードは compose + 正の `--drain-grace-sec`

`--drain-grace-sec` の既定は 0 で、セッションが終わると runner が終了する。これでは「コンテナ内で起動しておき、そこで実行させる」という常駐の検証にならないので、正の値（例: 3600）を与えて同一プロセスがポーリングを続けるようにする。`restart: always` は落ちたときの保険。

- この設定は「config スナップショットが起動時 1 回」という制約と直結する。ワークスペースを編集したら `docker compose restart` が必要で、これは手順書に明記する（spec: config の変更は runner 再起動で反映される）。

### D7: セッション毎モードは orchestrator + 差し替え可能なプロビジョナ

orchestrator が呼ぶフックは、ドキュメントの規定どおり `${hooks-dir}/spawn-runner` という名前でなければならない。ここに Docker のコマンドを直接書くと、実運用で想定している GKE Pod への移行時に書き直しになる。そこで **2 層に分ける**。

- `spawn-runner`（薄いディスパッチャ、Anthropic 側の契約を引き受ける）
  - `CLAUDE_RUNNER_*` 変数を読み、`CLAUDE_RUNNER_WORK_ORDER_FILE` の**中身**を読み出す（フック終了時にファイルが消えるため、パスではなく値を運ぶ）。
  - 後述の内部契約に正規化して、`RUNNER_SPAWN_BACKEND` が指すバックエンドスクリプトを `exec` する。
  - バックエンドの終了コードをそのまま orchestrator へ返す。
- `provisioners/docker.sh`（検証用バックエンド）、`provisioners/gke.sh`（実運用用、今回は雛形のみ）

**内部契約**（ディスパッチャ → バックエンド）。バックエンドはこれだけを入力とし、`CLAUDE_RUNNER_*` を直接読まない。

| 渡し方 | 名前 | 内容 |
| :-- | :-- | :-- |
| stdin | — | work-order JWT（1 行）。引数にも環境変数にも置かない |
| env | `SPAWN_ORDER_ID` | 冪等キー。リソース名として安全な文字列 |
| env | `SPAWN_RUNNER_IMAGE` | 起動するイメージ |
| env | `SPAWN_RUNNER_ARGS` | runner に渡す引数列（`--capacity 1 --base-dir ...` など、モード A と揃える） |
| env | `SPAWN_RUNNER_MOUNTS` | 付けるもの（`<source>:<container-path>:<ro\|rw>` の並び）。資格情報は `ro`、イベントログは `rw`。プロビジョナが自分の記法へ変換する。D12 / D13 |
| env | `SPAWN_SESSION_ID` | ログ用。pre-warming 要求では空 |

バックエンドが守る規約は 3 つで、これは provisioner に依存しない。

1. **`SPAWN_ORDER_ID` で冪等**。同じ ID の再配信で起動するワークロードは高々 1 つ。名前を ID から決定的に導き、プラットフォーム側の重複拒否に任せる（Docker なら `--name`、GKE なら Job 名）。
2. **リトライしない**。1 order = 高々 1 ワークロード。登録されなければ Anthropic 側が新しい order ID で再要求する。
3. **終了コード**: 0 = 投入済み、1 = リトライ可能な失敗、2 以上 = リトライ不可。stderr には原因だけを書き、秘密情報を書かない。

`docker.sh` の実装方針: JWT を stdin から読み、`umask 077` で作った一時 env ファイルに `SELF_HOSTED_RUNNER_ENVIRONMENT_SECRET=` として書き、`docker run -d --rm --name ccr-$SPAWN_ORDER_ID --env-file ...` で起動して即座に削除する。同名コンテナが既に存在する場合は「投入済み」として exit 0。

`gke.sh` は今回実装しない。README に内部契約を書き、Job マニフェストを `SPAWN_ORDER_ID` 由来の名前で `kubectl apply`（`create` ではなく `apply` なら重複が自然に冪等）し、JWT を Secret として同名で作る、という移行メモだけ残す。

- pre-warming 要求では `CLAUDE_RUNNER_SESSION_ID` が空になるので、ディスパッチャは `set -u` 下で `${VAR:-}` で参照する。
- 代替案「`spawn-runner` に Docker を直書き」は行数は減るが、バックエンドを差し替えるときに Anthropic 側の契約（work-order ファイルの寿命、終了コードの意味、冪等性）を再実装することになるので却下。分けておけば、GKE 移行で書くのは `kubectl` 数行だけになり、契約側は検証済みのまま残る。
- 代替案「バックエンドにも `CLAUDE_RUNNER_*` をそのまま渡す」は却下。バックエンドが Anthropic のフック仕様に結合し、仕様変更が全バックエンドに波及する。

### D8: GitHub MCP はリモート HTTP、トークンは実行時注入

`.claude.json` に次の形で書く（entrypoint が `GITHUB_PAT` から生成）。

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer <GITHUB_PAT>" }
    }
  }
}
```

`claude mcp add --scope user` をイメージビルド時に実行する方法もドキュメントにあるが、それだと PAT がイメージレイヤに焼き付くので却下。entrypoint 生成なら値だけが実行時に入る。`GITHUB_PAT` 未設定なら entrypoint は非ゼロで終了する（黙って MCP なしで起動すると、検証で「MCP が見えない」原因の切り分けができなくなるため）。

### D9: セッション権限は auto モードを wrapper で固定

self-hosted セッションには端末がないため、権限プロンプトが出ると Web UI で人間が応答するまでターンが止まる。検証を止めないために、`--exec-path` の wrapper で `--permission-mode auto` を末尾に付ける。

```bash
exec "$CLAUDE_RUNNER_CLAUDE_BIN" "$@" --permission-mode auto
```

ドキュメントは auto モードの固定を default-deny egress とセットで推奨しているが、本検証は Non-Goals のとおりハードニング対象外。**検証用途に限る**ことを手順書に明記し、本番に転用しないよう注記する。

### D10: GCP 資格情報はワークスペース外の読み取り専用マウント

「セッションがこちらのコンテナで動いている」ことを確定させるため、**このコンテナにしか存在しない資格情報でしか到達できないリソース**を 1 つ用意する。BigQuery テーブル `nnyn-dev.house_monitor.co2`（既存）を対象にする。

- キーは `workspace/` の**外**、`/run/secrets/gcp-sa.json` に `:ro` でマウントし、`GOOGLE_APPLICATION_CREDENTIALS` で指す。セッションは runner の環境を継承するのでそのまま届く。
- ワークスペースに置かない理由は 2 つ。(a) ワークスペースは `/opt/claude-config` へコピーされセッションの config ディレクトリへ seed されるので、キーが増殖する。(b) ワークスペースは差し替え可能な検証データという位置付けで、資格情報とはライフサイクルが違う。
- イメージには `google-cloud-sdk`（`bq` / `gcloud`）を入れる。セッションがその場でスクリプトを書けるよう、手段だけ用意して中身は用意しない（spec: 自作スクリプトで実行場所を証明する）。
- egress に `oauth2.googleapis.com`（トークン取得）と `bigquery.googleapis.com` が加わる。

### D11: サービスアカウントは Terraform、キー発行は人間

`terraform/` は `nnyn-dev` にサービスアカウントと IAM バインディングだけを作る。

- `account_id` = `test-claude-self-hosted-env`。希望の `test-claude-self-hosted-environment` は 35 文字で、GCP のサービスアカウント ID 上限 30 文字（6〜30、小文字・数字・ハイフン）を超えるため縮めた。`display_name` にはフルネーム `test-claude-self-hosted-environment` を入れて意図を残す。メールは `test-claude-self-hosted-env@nnyn-dev.iam.gserviceaccount.com`。
- 権限は 2 つに分ける。クエリ実行はジョブ単位なのでプロジェクトレベルの `roles/bigquery.jobUser`、データ読み取りは**テーブルレベル**の `google_bigquery_table_iam_member` で `roles/bigquery.dataViewer`。データセットレベルにしないのは、同一データセットの他テーブルが読めてしまい「対象外は読めない」というシナリオが成立しなくなるため。
- **キーは Terraform で作らない。** `google_service_account_key` はプライベートキーを平文で tfstate に書き込む。人間が `gcloud iam service-accounts keys create` で発行し、git 管理外に置く（README の人間セットアップ項目）。
- 既存テーブルは Terraform の管理下に置かない。IAM バインディングのみ付け、テーブル自体は `data` 参照にとどめる。

### D12: 内部契約に `SPAWN_RUNNER_MOUNTS` を追加

D10 のマウントはモード B でも必要になる。マウントの記法はプロビジョナ固有（Docker は `-v`、GKE は Volume + Secret）なので、ディスパッチャは**何を何処へ読み取り専用で付けるか**だけを provisioner 非依存の形で渡し、各プロビジョナが自分の記法へ変換する。D7 の内部契約表に `SPAWN_RUNNER_MOUNTS`（`<source>:<container-path>:ro` の並び）を追加する。

### D13: イベントは JSONL でホスト側のログファイルに追記する

セッション毎ワークスペースの永続化を実装する前に、**永続化に必要なイベントが取れるか**だけを先に確かめる。永続化そのものは実装せず、各イベント点にログ出力だけを仕込む。

イベント面は 2 つある。

**(1) runner レベル（`--hooks-dir` のライフサイクルフック）**

| イベント | 取れるもの | 永続化にとっての意味 |
| :-- | :-- | :-- |
| `spawn-runner` | order ID、session ID、repo URL | モード B でワークロードを作る直前。永続ボリュームを割り当てるならここ |
| セッション開始（`--exec-path` の wrapper） | session ID、config dir、引数 | ワークスペースが用意された直後 |
| `post-session` | `CLAUDE_RUNNER_WORKSPACE_PATHS`（`:` 区切りの作業ツリー）、`CLAUDE_RUNNER_EXIT_REASON`、`CLAUDE_RUNNER_DEBUG_LOG_PATH` | **永続化の本命**。ドキュメントいわく「未コミットの作業を救う唯一の機会」。ワークスペース破棄の**前**に走る |

`post-session` の性質で、検証で確かめるべき点が 3 つある。

- 子プロセスが起動したセッション終了では**毎回**発火する。`CLAUDE_RUNNER_EXIT_REASON` は `completed` / `failed` / `interrupted` のいずれか（`abandoned` は現状発火しない）。`completed` 以外でも取れるかを実際に確かめる。
- フックの終了コードはセッション結果に影響しない。失敗はログされて無視される。つまり**永続化が失敗しても気づけない**ので、成否を自前でログに残す必要がある。
- タイムアウトは `--post-session-hook-timeout-sec`（既定 60 秒）。永続化の所要時間がここに収まるかを見るため、ログに所要ミリ秒を残す。
- runner が異常終了した場合（VM の強制停止など）は発火しない。

**(2) セッション内（Claude Code hooks）**

runner の異常終了に備えるには、ドキュメントはセッション内の `PostToolUse` フックで定期スナップショットを取れと言っている。これが本当に動くかも確かめる必要があるので、seed されるワークスペースの `.claude/settings.json` に `SessionStart` / `PostToolUse` / `Stop` / `SessionEnd` を仕込み、同じログファイルへ追記する。**イベントごとにシェルスクリプトが実行できる**ことの確認は、この面で取る。

**ログの置き場と形式**

ホスト側のディレクトリを `/var/log/ccr-events` に **rw** でマウントし、`events.jsonl` に 1 イベント 1 行の JSON を追記する。モード B のコンテナは使い捨てなのでコンテナ内に書くと消える。共通フィールドは `ts` / `event` / `session_id`、イベント固有に `exit_reason` / `workspace_paths` / `duration_ms` など。

永続化の実現可能性を後で判断できるよう、`post-session` では**その時点でワークスペースがまだ在るか**を記録する（各パスの存在、ファイル数、`git status --porcelain` の行数）。永続化はせず、「ここで救えたはずか」だけを残す。

秘密情報（work-order JWT、`CLAUDE_CODE_SESSION_ACCESS_TOKEN`、GitHub PAT、SA キー）はログに書かない。

### D14: `checkout` フックは本編とは別に単独で検証する

`checkout` フックは組み込みのクローンを**置き換える**。一方 D4 では `--use-anthropic-git-proxy` を使っており、この経路ではフックに git 資格情報が渡らない。つまり `checkout` フックを常設すると D4 が成立しなくなる。

そこで `checkout` は本編の 2 モードには入れず、**公開リポジトリを対象にした単発の検証**として切り出す。公開リポジトリなら資格情報なしで `git clone` できるので、フックが自前でクローンしつつログも残せる。ここで確認したいのは「リポジトリ準備の段階に介入できるか」だけで、永続化の本命は `post-session` 側にある。

- 代替案「本編でも `checkout` を常設し、フック内でセッショントークンから短命の clone 資格情報を発行する」は、資格情報サービスを別途立てることになり検証の範囲を大きく超えるので却下。

### D15: `command` フックは使わない

`--exec-path` を設定すると `command` フックは無視される、とドキュメントに明記されている。D9 で `--exec-path` を使うため、セッション開始のログは wrapper 側に置く。`hooks/` に `command` を置いても動かないので、置かない。README にこの排他関係を書く。

## ディレクトリ構成

```
container/
  Dockerfile           # D1, D3, D4 の前提を満たすイメージ
  entrypoint.sh        # ワークスペースのコピー + .claude.json 生成 + runner/orchestrator 起動
  session-wrapper.sh   # D9
  hooks/
    spawn-runner       # D7: orchestrator のフック（実行可能）。契約の引き受けと正規化だけ
    post-session       # D13: 永続化の本命。何が救えたはずかをログに残す（救わない）
  log-event.sh         # D13: JSONL を追記する共通スクリプト。全フックが呼ぶ
  checkout-probe/
    checkout           # D14: 単発検証用。公開リポジトリを自前で clone しつつログを残す
  provisioners/
    docker.sh          # D7: 検証用バックエンド（実行可能）
    gke.sh.example     # D7: GKE Job 移行用の雛形。今回は実装しない
  compose.persistent.yaml   # モードA
  compose.ondemand.yaml     # モードB（orchestrator）
  .env.example         # 人間が埋める変数の雛形
terraform/
  main.tf              # D11: SA + IAM バインディング（既存テーブルは data 参照）
  variables.tf
  outputs.tf           # SA のメールアドレス。キーは出力しない
workspace/
  .claude/
    skills/what-is-pentelpantel/SKILL.md   # 既存
    settings.json      # D13: SessionStart / PostToolUse / Stop / SessionEnd のフック定義
README.md              # 構成・人間のセットアップ項目・検証手順・結果記録表
```

`entrypoint.sh` は第 1 引数で `runner` / `orchestrator` を切り替える。共通の前処理（コピーと `.claude.json` 生成）は両方で走らせる — orchestrator 自身は config を使わないが、同じイメージを使い回すため分岐を最小にする。

## Risks / Trade-offs

- **`.claude.json` の探索先の解釈違い** → D1 の二重書き込みで吸収。どちらが効いたかは runner のログ（`--log-level debug`）で確認し、結果を記録する。
- **Docker ソケットのマウント（D7）はホストへの実質 root 権限** → 検証環境に限定する。実運用では `provisioners/gke.sh` に差し替えることで、ソケットマウントごと不要になる。orchestrator コンテナはセッションコードを実行しないので、露出面は「セッションが orchestrator に触れない限り」に留まる。
- **バックエンドを 2 層に分けた分、検証するのは Docker 実装だけになる** → 内部契約が GKE でも成立するかは検証されない。契約を README に明文化し、`gke.sh.example` を雛形として置くことで、移行時に埋めるべき箇所を先に見えるようにしておく。
- **`docker run` に渡した環境変数は `docker inspect` に残る** → 一時 env ファイルを消しても JWT はコンテナ設定に残る。work-order JWT は単一 runner の登録に使い切りで期限も短いため検証では許容し、環境 secret はそもそも渡さない（そちらが本命の分離）。
- **auto モード固定（D9）はネットワーク境界なしで無人実行される** → 検証用途限定の注記。検証用リポジトリは書き込み権限の小さいものを使う。
- **全セッションがワークスペースを共有する** → ユーザ合意済みの省略。並行セッションで skill を編集すると相互に影響するが、`--capacity 1` かつ config はスナップショットなので実害は起動タイミングに限られる。
- **サービスアカウントキーは長期資格情報** → 検証終了後に鍵を失効させることを README の片付け手順に入れる。権限が 1 テーブルの読み取りとクエリ実行に限られているため、漏洩時の影響は限定的。
- **BigQuery アクセスの失敗が多義的**（資格情報が届いていない / 権限不足 / egress 遮断） → 切り分けできるよう、README に 3 つのエラーの見分け方を書く（spec: 失敗が切り分けられる）。
- **`post-session` の終了コードは無視される** → 永続化を実装しても失敗に気づけない。ログに成否と所要時間を残す設計にし、将来の実装では監視を別に用意する必要があることを README に書く。
- **セッション解放時のタイミングに競合がある** → プロンプト待ちで解放された場合は「解放 → `post-session`」の順になり、フック実行中に別 runner でセッションが再開しうる。この順序では永続化と再開が競合する。検証ではアイドル解放とプロンプト待ち解放の両方を起こしてログの順序を記録する。
- **runner の異常終了では `post-session` が発火しない** → セッション内の `PostToolUse` による定期スナップショットが代替手段になる。今回はそのフックが発火することの確認までを行う。
- **beta 機能でフラグ名・挙動が変わりうる** → Claude Code のバージョンをビルド引数で固定し（v2.1.267 以降を想定）、検証時のバージョンを結果に記録する。
- **`api.githubcopilot.com` への egress が必要** → 遮断環境ではローカル stdio の `github-mcp-server` に切り替える必要がある。今回はユーザ選択によりリモート HTTP を採る。

## Migration Plan

新規構築のため移行なし。撤収は、コンテナと生成イメージを削除し、claude.ai 側で environment を削除、GitHub PAT を失効させる。

## Open Questions

- 永続化の実装方式（`post-session` でのスナップショットブランチ push か、永続ボリュームの再利用か）。本 change ではイベントが取れることの確認までなので、方式の決定は次の change に委ねる。ログに残す情報はどちらの方式でも判断材料になるよう選んである。

- 検証に使う GitHub リポジトリをどれにするか（公開リポジトリで足りるか、PAT のスコープをどこまで絞れるか）。手順書の記述時に埋めれば足り、設計もタスク分割も変わらない。
