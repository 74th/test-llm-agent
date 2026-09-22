# Proposal

## Why

Claude Managed Agents をプロダクションで使う前に、「Anthropic のクラウドサンドボックスではなく、自前のコンテナ環境でエージェントのツールを実行できるのか」を実地で確かめる必要がある。特に、コンテナ内にしか存在しない資格情報（GCP サービスアカウントキー）で実作業ができること、指定した skills / MCP がエージェントに認識されること、そしてセッション単位でコンテナを起動・終了させる運用（将来のワークスペース永続化の土台）が成立することを、動く検証ハーネスとして残したい。

## What Changes

- `config: {type: "self_hosted"}` の Environment を作成し、ローカル（または任意のホスト）の Docker コンテナでツール実行を行う検証ハーネスを新規に構築する。
- ワーカーの起動方式を 2 モード用意する。
  - **モード A（常駐単一コンテナ）**: 1 つのコンテナが `EnvironmentWorker.run()` でポーリングし続け、全セッションを同じコンテナで処理する。
  - **モード B（セッション毎コンテナ）**: ホスト側のオーケストレータが work item をポーリングし、work item ごとに `docker run` で使い捨てコンテナを起動、その中で `EnvironmentWorker.handle_item()` を 1 件だけ処理して終了する。
- モード B のコンテナ起動・終了を **JSON Lines のライフサイクルログ**として記録する。将来のワークスペース永続化フックの接続点になる。セッション ID / work ID / 開始・終了時刻 / 終了コードを残す。
- Claude API を叩いて Agent を登録・更新するプロビジョニングスクリプトを追加する。ローカルの `skills/` ディレクトリを Skills API にアップロードし、`mcp.json` の宣言を Agent の `mcp_servers` + `mcp_toolset` に反映し、返った agent ID を永続化する。
- GitHub の hosted MCP サーバを検証対象とし、GitHub PAT を vault credential として登録してセッションに紐付ける。
- GCP サービスアカウントキーをコンテナにマウントし、エージェントが「その場で BigQuery にアクセスするスクリプトを書いて実行する」ことで、コンテナ内の資格情報で作業していることを確定させる。対象は既存テーブル `nnyn-dev.house_monitor.co2`。
- `terraform/` 配下に、`nnyn-dev` プロジェクトで当該テーブルへの読み取り権限とクエリ実行権限だけを持つサービスアカウントを作る Terraform 構成を追加する。
- `README.md` に、構成図・検証手順・人間が事前に設定すべきこと・人間が目視で確認すべきことを記載する。

これは新規の検証用ハーネスであり、既存の振る舞いを壊す変更はない。

## Capabilities

### New Capabilities

- `self-hosted-environment`: 自前コンテナでツール実行を行う Managed Agents 環境と、モード A / モード B の 2 つのワーカー起動方式。
- `container-lifecycle-log`: セッション毎コンテナの起動・終了イベントを構造化ログとして残す仕組み。
- `agent-provisioning`: Claude API 経由での Agent 登録、skills のアップロードと添付、MCP サーバ宣言、vault credential の登録。
- `bigquery-access-verification`: コンテナ内にマウントした GCP サービスアカウントキーでの BigQuery アクセス検証と、その権限を作る Terraform 構成。
- `verification-guide`: 構成・検証手順・人間側の事前設定・人間側の確認項目を記した README。

### Modified Capabilities

（なし。プロジェクトに既存の spec はない）

## Impact

- 新規ディレクトリ: `worker/`（Python ワーカーとオーケストレータ）、`scripts/`（プロビジョニングと検証実行）、`skills/`（検証用カスタムスキル）、`terraform/`、`docker/`。
- 新規ファイル: `mcp.json`、`README.md`、`pyproject.toml`（または `requirements.txt`）。
- 外部依存: Anthropic Python SDK、`google-cloud-bigquery`、Docker、Terraform、`gcloud`。
- 人間側の事前設定が必須: Anthropic API キー、Console での environment key 発行、GitHub PAT、GCP プロジェクト `nnyn-dev` への Terraform 適用権限。
- 制約として確定済み: self-hosted 環境では vault の `environment_variable` credential、および `file` / `github_repository` リソース（= リポジトリ内 `.claude/skills` の自動探索）が使えない。skills は Skills API 経由のアップロード、GCP キーは Docker のマウントで供給する。
