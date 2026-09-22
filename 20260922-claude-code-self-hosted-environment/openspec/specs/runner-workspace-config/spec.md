# runner-workspace-config Specification

## Purpose

コンテナにマウントしたワークスペースを runner の host config として使い、そこに置いた skills と MCP サーバ定義を各セッションへ届けるための、ディレクトリ構造と生成の振る舞いを定める。

## Requirements

### Requirement: マウントされたワークスペースが host config として使われる

runner は、既定の `~/.claude` ではなく、マウントされたワークスペース配下の config ディレクトリをセッションへ seed しなければならない（SHALL）。この向き先は runner プロセスの環境変数で指定される（SHALL）。

#### Scenario: config ディレクトリが差し替わっている

- **WHEN** runner プロセスの環境を確認する
- **THEN** host config ディレクトリがマウントしたワークスペース配下のパスを指している

### Requirement: ワークスペースの skill がセッションで利用できる

ワークスペースの skills ディレクトリに置かれた skill は、そのセッションが扱うリポジトリに何も追加することなく、セッション内の Claude から認識・実行できなければならない（SHALL）。

#### Scenario: skill の内容を答えられる

- **WHEN** セッション内の Claude に「ペンテルパンテルとは何か」を尋ねる
- **THEN** Claude は `what-is-pentelpantel` skill を読み込み、74th の自作キーボードで左右と中央テンキーの 3 分割であるという内容を答える

#### Scenario: skill が一覧に現れる

- **WHEN** セッション内の Claude に利用可能な skill を列挙させる
- **THEN** `what-is-pentelpantel` が含まれる

### Requirement: GitHub MCP サーバがセッションで利用できる

GitHub MCP Server はリモート HTTP トランスポートでユーザスコープに定義され、各セッションへ seed されなければならない（SHALL）。定義はワークスペース側の設定ファイルに置かれ、セッションからは MCP ツールとして利用できる（SHALL）。

#### Scenario: MCP ツールが見える

- **WHEN** セッション内の Claude に利用可能な MCP ツールを列挙させる
- **THEN** GitHub MCP サーバのツールが含まれる

#### Scenario: MCP ツールが実際に応答する

- **WHEN** セッション内の Claude に GitHub MCP 経由で公開リポジトリの情報を取得させる
- **THEN** ツール呼び出しが成功し、リポジトリの情報が返る

### Requirement: GitHub の資格情報が実行時に注入される

GitHub MCP サーバの認証トークンは、ワークスペースの追跡対象ファイルにもイメージにも保存されてはならない（MUST NOT）。トークンはコンテナ起動時に環境変数から読み取られ、runner 起動前に MCP 設定ファイルへ書き込まれる（SHALL）。トークンが与えられていない場合、コンテナは MCP 設定を壊したまま起動するのではなく、明示的なエラーで失敗する（SHALL）。

#### Scenario: トークンから設定が生成される

- **WHEN** GitHub トークンを環境変数で与えてコンテナを起動する
- **THEN** host config ディレクトリに GitHub MCP の定義を含む設定ファイルが生成され、その値に与えたトークンが使われる

#### Scenario: トークン未設定で失敗する

- **WHEN** GitHub トークンを与えずにコンテナを起動する
- **THEN** コンテナは不足している変数名を示すエラーメッセージを出して非ゼロで終了する

#### Scenario: 生成物がリポジトリに残らない

- **WHEN** コンテナ起動後にリポジトリの git status を確認する
- **THEN** 生成された MCP 設定ファイルは追跡対象として現れない

### Requirement: config の変更は runner 再起動で反映される

runner は起動時に一度だけ host config をスナップショットするため、ワークスペース上の skills や MCP 定義を編集した場合、その変更は runner を再起動するまでセッションへ反映されない。この制約は運用手順に明記されなければならない（SHALL）。

#### Scenario: 再起動なしでは反映されない

- **WHEN** runner を起動したままワークスペースに新しい skill を追加し、新しいセッションを開始する
- **THEN** その skill はセッションから見えない

#### Scenario: 再起動後に反映される

- **WHEN** runner を再起動してから新しいセッションを開始する
- **THEN** 追加した skill がセッションから見える
