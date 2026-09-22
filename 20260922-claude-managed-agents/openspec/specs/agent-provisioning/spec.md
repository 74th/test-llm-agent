# agent-provisioning Specification

## Purpose

Claude API 経由で Agent・Environment・カスタム skills・MCP サーバ宣言・vault credential を登録し、検証に必要な構成を再現可能な形でプロビジョニングする。

## Requirements

### Requirement: Agent と Environment のプロビジョニング

システムは、Agent と self-hosted Environment を Claude API 経由で作成し、作成した ID を永続化するスクリプトを提供しなければならない（SHALL）。Agent は一度だけ作成し、以降は更新（バージョン追加）で構成を変更する。

#### Scenario: 初回実行で Agent と Environment が作られる

- **WHEN** ID が保存されていない状態でプロビジョニングスクリプトを実行する
- **THEN** self-hosted Environment と Agent が作成され、それぞれの ID（および Agent のバージョン）がローカルの設定ファイルに保存される

#### Scenario: 再実行で重複作成されない

- **WHEN** ID が保存済みの状態で同じスクリプトを再実行する
- **THEN** 新しい Agent / Environment は作成されず、既存の Agent が更新されて新しいバージョンが払い出される

#### Scenario: セッション作成時にモデルやツールを渡さない

- **WHEN** セッションを作成する
- **THEN** `model` / `system` / `tools` / `mcp_servers` / `skills` はセッションではなく Agent 側に定義されており、セッションは Agent への参照と Environment ID のみを渡す

#### Scenario: 使用モデルが既定で Claude Opus 5 である

- **WHEN** Agent の構成を照会する
- **THEN** モデルが `claude-opus-5` であり、設定で上書きできる

### Requirement: カスタム skills の登録と添付

システムは、ローカルの skills ディレクトリにあるスキル定義を Skills API にアップロードし、そのスキルを Agent に添付しなければならない（SHALL）。self-hosted 環境ではリポジトリの `.claude/skills` 自動探索が使えないため、アップロード経由であることが前提となる。

#### Scenario: ローカルのスキルがアップロードされる

- **WHEN** `SKILL.md` を含むスキルディレクトリを置いてプロビジョニングスクリプトを実行する
- **THEN** そのスキルが Skills API に作成され、返った skill ID が Agent の `skills` に添付される

#### Scenario: スキル内容の更新が新バージョンになる

- **WHEN** `SKILL.md` を編集して再実行する
- **THEN** 既存スキルの新しいバージョンが作成され、Agent はそのバージョンを参照する

#### Scenario: エージェントがスキルを認識している

- **WHEN** セッションでエージェントに、利用可能なスキルの名前と説明を尋ねる
- **THEN** アップロードした検証用スキルの名前と説明が返る

#### Scenario: エージェントがスキルの内容に従って振る舞う

- **WHEN** 検証用スキルが対象とするタスクをエージェントに依頼する
- **THEN** エージェントはスキルに書かれた手順・出力形式に従った結果を返し、スキルが読み込まれたことが出力から判別できる

### Requirement: MCP サーバの宣言と認証

システムは、`mcp.json` に宣言された MCP サーバを Agent の `mcp_servers` と対応する `mcp_toolset` に反映し、その認証情報を vault credential として登録してセッションに紐付けなければならない（SHALL）。Managed Agents の MCP は URL（Streamable HTTP）形式のみを受け付ける。

#### Scenario: mcp.json の宣言が Agent に反映される

- **WHEN** `mcp.json` に GitHub の hosted MCP サーバを宣言してプロビジョニングスクリプトを実行する
- **THEN** Agent の `mcp_servers` に `type` / `name` / `url` が登録され、同名を参照する `mcp_toolset` が `tools` に追加される

#### Scenario: URL 形式でないサーバ宣言は拒否される

- **WHEN** `mcp.json` にローカル実行（stdio）形式のサーバを宣言する
- **THEN** スクリプトは明示的なエラーメッセージで失敗し、Agent を不正な状態で更新しない

#### Scenario: 認証情報が vault に登録される

- **WHEN** GitHub のトークンを設定してプロビジョニングスクリプトを実行する
- **THEN** vault と credential が作成され、credential は MCP サーバの URL に紐付き、トークンの値は API レスポンスに含まれない

#### Scenario: セッションに vault が紐付く

- **WHEN** セッションを作成する
- **THEN** 作成した vault の ID が `vault_ids` として渡される

#### Scenario: エージェントが MCP のツールを認識している

- **WHEN** セッションでエージェントに、利用可能な MCP のツール名を列挙させる
- **THEN** GitHub MCP サーバが提供するツールが列挙される

#### Scenario: MCP のツール呼び出しが承認を経て成立する

- **WHEN** エージェントに GitHub MCP のツールを 1 つ実際に使わせる
- **THEN** MCP の既定の権限ポリシーによりセッションが承認待ちで停止し、承認を返すとツールが実行されて結果がエージェントに渡る

### Requirement: プロビジョニングの前提チェック

システムは、セッションを開始する前に、必要な資格情報と構成が揃っているかを検査し、不足を具体的に報告しなければならない（SHALL）。

#### Scenario: 不足している資格情報が名前で報告される

- **WHEN** 必要な資格情報（Anthropic API キー、environment key、GitHub トークン、GCP キーのパス）のいずれかが欠けた状態で実行する
- **THEN** 欠けている項目の名前と設定方法を含むエラーが出力され、Agent や Environment を作成しないまま終了する
