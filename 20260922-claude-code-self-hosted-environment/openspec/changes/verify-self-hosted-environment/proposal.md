# Proposal

## Why

Claude Team/Enterprise の Self-hosted Environment（public beta）では、cloud session を自社インフラ上の runner で実行できる。このリポジトリでは「独自コンテナイメージで runner を動かしたとき、コンテナ側に用意した skills と MCP サーバがセッションから実際に見えるのか」を、実機で確かめたい。ドキュメント上は runner 起動時に host config をスナップショットしてセッションに seed する仕組みだと読めるが、マウントしたワークスペースを config 元にできるか・`.claude.json` の探索先がどこになるかは実際に動かさないと確定しない。

## What Changes

- `container/` を新設し、self-hosted runner を動かす独自イメージの構築リソースを置く。
  - `Dockerfile`: Debian ベース + 固定バージョンの `claude` バイナリ + git 設定。
  - `entrypoint.sh`: マウントされたワークスペースから host config ディレクトリを整え、GitHub MCP の `.claude.json` を実行時のトークンから生成してから runner / orchestrator を起動する。
- `workspace/` を「コンテナにマウントする host config ワークスペース」として確定させる。
  - 既存の `workspace/.claude/skills/what-is-pentelpantel/SKILL.md` を検証用スキルとして使う。
  - GitHub MCP Server（リモート HTTP、`https://api.githubcopilot.com/mcp/`）をセッションに届ける設定をここに置く。トークンはイメージにも `workspace/` にも焼き込まず、実行時の環境変数から `entrypoint.sh` が生成する。
- 2 つの実行モードをどちらも立ち上げられるようにする。
  - **常駐モード**: `docker compose` で runner コンテナを常駐させ、`--drain-grace-sec` を正の値にして同一コンテナが連続してセッションを拾う。
  - **セッション毎モード**: `claude self-hosted-runner orchestrator` を常駐させ、`spawn-runner` フックが要求ごとにセッション専用ワークロードを 1 つ起動する（`--capacity 1`）。フックは Anthropic 側の契約を引き受ける層と、実際にワークロードを起動するプロビジョナ層に分け、検証では Docker のプロビジョナを使う。実運用で想定している GKE Pod へはプロビジョナの差し替えだけで移れるようにする。
- `terraform/` を新設し、GCP プロジェクト `nnyn-dev` に検証用サービスアカウントを作る。BigQuery のクエリ実行権限（プロジェクトレベル）と、テーブル `nnyn-dev.house_monitor.co2` への読み取り権限（テーブルレベル）のみを与える。
- サービスアカウントキーをコンテナに読み取り専用でマウントし、`GOOGLE_APPLICATION_CREDENTIALS` でセッションへ渡す。ワークスペースの外に置き、リポジトリにもイメージにも入れない。
- **実行場所の証明**を検証項目に追加する。このキーはこのコンテナにしか存在しないため、セッションがその場で BigQuery アクセスのスクリプトを書いて `nnyn-dev.house_monitor.co2` を引けたなら、そのセッションは確かにこのコンテナ内のリソースで動いている。
- **ライフサイクルイベントの観測**を追加する。セッション毎ワークスペースの永続化に必要なイベントが実際に取れるかを先に確かめるため、runner レベルのフック（ワークロード起動要求・セッション開始・セッション終了）とセッション内の Claude Code フック（開始・ツール実行後・応答完了・終了）に、JSONL をホスト側ログへ追記するスクリプトを仕込む。**永続化そのものは実装しない。** セッション終了イベントでは、その時点でワークスペースが在ったか・未コミットの変更があったか・フックの所要時間を残し、後から実装可否を判断できるようにする。
- リポジトリ直下に `README.md` を新設し、検証の単一の入口にする。「構成」「人間が設定すべき内容（environment の作成、environment key の取得、GitHub 連携、PAT 発行）」「検証手順」「人間が検証すべき内容（claude.ai に投げるプロンプトと合格条件）」の 4 セクションを持たせる。
- 検証結果は README 内のマトリクス表に記録し、「skills が認識されたか」「MCP tool が見えたか」をモードごとに残す。

この change は検証環境の構築と手順の定義、およびイベントが取れることの確認までを対象とする。ワークスペース永続化の実装は、イベントが取れると分かってから別の change で行う。`terraform apply` の実行と BigQuery テーブルの作成は人間の作業とし、テーブルは既存のものを使う。実際にプロンプトを投げる操作は claude.ai の Web UI からしか行えないため、人間の作業として手順に含める。

## Capabilities

### New Capabilities

- `self-hosted-runner-container`: 独自コンテナイメージで self-hosted runner を動かすための、イメージ構築・設定 seed・2 つの実行モードの要件。
- `runner-workspace-config`: マウントされたワークスペースから skills と MCP 設定をセッションへ届けるための、host config ディレクトリの構造と生成要件。
- `self-hosted-verification-procedure`: 人間のセットアップ項目と、skills / MCP が効いていることを確認する検証手順の要件。
- `container-execution-evidence`: セッションがこのコンテナ内のリソースで動いていることを証明するための、GCP 資格情報の供給範囲と証明手順の要件。
- `session-lifecycle-events`: セッション毎ワークスペースの永続化を将来実装できるかを判断するための、ライフサイクルイベントの観測とログ記録の要件。

### Modified Capabilities

（なし。このプロジェクトにはまだ spec が存在しない。）

## Impact

- 新規ディレクトリ: `container/`（`Dockerfile`, `entrypoint.sh`, `session-wrapper.sh`, `hooks/spawn-runner`, `provisioners/`, compose ファイル）。新規ファイル: リポジトリ直下の `README.md`。
- 既存 `workspace/` の位置付けが「runner の host config ディレクトリの親」として確定する。ディレクトリ構成が変わる可能性がある。
- 新規ディレクトリ: `terraform/`（`nnyn-dev` のサービスアカウントと IAM バインディング）。
- 外部依存: Claude Code バイナリ（`downloads.claude.ai` から固定バージョンを取得）、`api.anthropic.com`、`github.com`、`api.githubcopilot.com`、`oauth2.googleapis.com`、`bigquery.googleapis.com` への egress。
- 既存の GCP リソースへの参照: BigQuery テーブル `nnyn-dev.house_monitor.co2`（既存。terraform では作らず、IAM バインディングのみ付ける）。
- 人間側の前提: Team/Enterprise の Owner ロールで **Allow self-hosted environments** を有効化し、environment key を発行すること。GitHub 連携と GitHub PAT の発行。`nnyn-dev` に対する terraform apply 権限と、サービスアカウントキーの発行。
- セキュリティ: environment secret、GitHub PAT、GCP サービスアカウントキーはイメージに焼き込まず、secret ファイル / 環境変数 / 読み取り専用マウントで渡す。検証用途のため本番ハードニング（default-deny egress など）は適用範囲外とし、その旨を明記する。
