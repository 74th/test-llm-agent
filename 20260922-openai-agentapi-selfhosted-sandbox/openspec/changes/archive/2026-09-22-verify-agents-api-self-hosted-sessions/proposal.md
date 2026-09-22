# Proposal

## Why

Claude Managed Agents で確認した「自前環境でのツール実行」「セッションごとのコンテナ」「対話再開時に使えるセッション識別情報」が、OpenAI Agents API の self-hosted environment でも成立するかを実測したい。今後のセッション単位のワークスペース永続化を設計するため、会話状態とコンテナ内ファイル状態の境界も明らかにする。

## What Changes

- OpenAI Agents API の `self_hosted` セッションと、自前 Docker コンテナ内の `codex exec-server` を接続する最小の検証ハーネスを作る。
- セッションごとにコンテナを割り当て、複数セッションの同時起動、終了、同じセッションでのコンテナ再起動を追跡する。
- セッション ID、環境 ID、コンテナ ID とライフサイクルを記録し、対話再開と将来のワークスペース復元に使える識別子を確認する。
- 再現手順、合否基準、実測結果と制約を文書化する。ワークスペースの永続化そのものは今回実装しない。

## Capabilities

### New Capabilities

- `self-hosted-tool-execution`: Agents API から要求されたツール操作が自前コンテナで実行されたことを検証できる。
- `session-container-lifecycle`: セッション単位でコンテナを起動・停止・再接続し、対応関係と終了理由を記録できる。
- `session-continuity-verification`: 同一セッションへの追加入力と新規セッションの区別、再開時に使える識別情報、ファイル状態の境界を検証できる。

### Modified Capabilities

なし。既存の OpenSpec capability はない。

## Impact

- このリポジトリは現時点で OpenSpec 設定と検証依頼のみのため、Docker イメージ、検証用アプリ、テスト、README を新規追加する計画。
- OpenAI Agents API と Codex executor、OpenAI SDK、Docker を使用する。アプリ用 API キーと executor 用の制限付き環境キーを分けて扱う。
- 参考にする Claude Managed Agents の検証は別リポジトリにあり、そのコードや追加の MCP・BigQuery 検証は今回の必須範囲に含めない。
