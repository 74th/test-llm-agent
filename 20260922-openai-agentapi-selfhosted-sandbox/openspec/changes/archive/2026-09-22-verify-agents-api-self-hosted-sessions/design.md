# Design

## Context

このリポジトリにはアプリケーション実装も既存 capability もない。参考リポジトリの Claude Managed Agents 検証は Python、Docker、ライフサイクルログを使っているが、OpenAI Agents API の self-hosted 接続は別の仕組みである。OpenAI 側がエージェントのループと会話を保持し、自前環境の `codex exec-server` がツール操作を実行する。[Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

OpenAI のドキュメントでは、各セッションに固有の環境 ID があり、そのセッションの `remote_url` とともに executor に渡す。セッションは環境より長く存続できる一方、環境 ID の再使用だけで新しいコンテナにファイルは復元されない。[Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted), [Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)

## Goals / Non-Goals

**Goals:**

- ローカル Docker ホストで、セッションとコンテナの 1 対 1 の稼働中対応を検証できる構成にする。
- コントローラを終了して再実行しても、保存したセッション ID から同じ会話に追加入力できるようにする。
- 将来のワークスペース保存・復元のため、起動前と停止前に参照できる ID と処理位置を実測する。

**Non-Goals:**

- 永続ボリューム、スナップショット、ファイル復元の実装。
- Webhook 常駐サービス、クラウドのコンテナ基盤、MCP・BigQuery・skill の検証。

## Decisions

### D1. アプリ管理型の Docker コントローラ

ホスト側の Python CLI が OpenAI SDK でセッションを作成・取得し、Docker を起動・監視する。単一のコントローラがセッション ID とコンテナ ID の対応を管理し、追加入力の前に必要なら executor を再起動する。Webhook 管理型も公式に用意されているが、今回のローカル実験では受信エンドポイントと署名検証が増えるため使わない。[Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)

CLI は `create`、`resume <session-id>`、`verify`、`stop <session-id>` 相当の操作を提供する。`create` は `environment.type: "self_hosted"` と `/workspace` を設定し、返されたセッション ID、環境 ID、`remote_url` をホスト側の非公開メタデータに保存する。`resume` は API から現行のセッションを取得して保存値を照合し、同じ環境 ID と `remote_url` で新しい executor を接続する。接続を確認してから入力する。`remote_url` は変更せず渡す。[Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

### D2. 1 セッションにつき稼働中コンテナ 1 個

Docker イメージには Codex CLI と `/workspace`、イメージ固有の読み取り用マーカーを置く。各コンテナは `codex exec-server --remote ... --environment-id ...` を実行する。セッション ID と環境 ID を Docker ラベルに付け、セッション単位の排他制御をかける。起動時にはラベルで既存コンテナを再照合してから作成し、同じセッションの重複起動を防ぐ。二つの異なるセッションは並行に起動できる。

初回実験では `/workspace` を永続マウントしない。再起動後に同じ会話が続くことと、ファイルが新コンテナへ自然には戻らないことを別々に観測する。復元フックの候補は Docker 起動直前、保存フックの候補は Docker 停止・削除の直前にある。将来の永続化ではこの位置でセッション ID をキーにストレージを関連付ける。

### D3. 停止はターン結果と入力競合の確認後

イベントストリームで `agent.session.turn.completed`、`failed`、`cancelled` と対象ツールの結果を追い、結果を API から再確認する。idle イベント単独では停止しない。セッション単位のロック内で追加入力の受付と停止を調停し、停止前に状態を再取得する。新しい実行要求があれば停止を取り消す。失敗時もコンテナとログを確実に後片付けする。公式ドキュメントは idle イベント単独の停止を危険とし、入力との調停を求めている。[Run and continue sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions), [Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)

イベントストリームの切断時にはセッションと保存済み items を取得して結果を復元し、欠落イベントが再送されると仮定しない。[Run and continue sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)

### D4. 資格情報と証拠を分けて扱う

ホストの `OPENAI_API_KEY` はセッション操作だけに使用し、コンテナへ渡さない。別途発行した制限付き環境キーをコンテナの `CODEX_API_KEY` に渡す。キーはイメージに焼き込まず、ログにも出さない。モデルは `OPENAI_MODEL` で指定し、権限・利用可否を実行前に確認する。環境キーは同一 organization、project、user または service account のものを使う。[Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

ホスト側に `logs/container-lifecycle.jsonl` を追記し、起動・接続・切断・停止・失敗の各イベントに UTC 時刻、セッション ID、環境 ID、コンテナ ID、終了コードを記録する。`run` ごとの検証結果は ID、マーカー照合、会話継続、ファイル境界、合否または未実施理由を含む。秘密値、会話中の合言葉、`remote_url` はログに残さない。保存メタデータとログは gitignore 対象にする。

### D5. 検証シナリオを固定する

`verify` は (1) マーカー読取とツール記録照合、(2) 2 セッション同時実行時のコンテナ分離、(3) 最初のターンで与えた合言葉を同一セッションの再起動後に尋ねる対話継続、(4) 新規セッションでの文脈分離、(5) マウントなしでのファイル非継続、を順に判定する。合言葉はファイルに書かず会話入力だけで渡す。実 API の結果とローカル模擬テストを区別して報告する。

## Risks / Trade-offs

- **API アクセスやモデル権限がない** → 実 API 検証は未実施として理由を示し、ローカルのコントローラテストのみ成功扱いにする。
- **停止・追加入力の競合で接続待ちが期限切れになる** → セッション単位の排他制御と状態再照合を行い、入力時の接続期限をログに残す。期限切れの入力を無条件に再送しない。[Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)
- **executor の切断で一部ツールが失敗する** → ターン完了だけで成功とせず、保存済みツール結果と最終回答を照合する。[Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)
- **コントローラ異常終了後にコンテナが残る** → Docker ラベルと API の現行状態を使って再起動時に照合し、所有するコンテナのみ回収する。

## Migration Plan

新規の検証ハーネスとして導入するため既存動作の移行はない。実験終了時は入力を止め、所有するコンテナを停止し、必要に応じて API セッションとローカル成果物を明示的に片付ける。セッション削除だけでは自前コンテナは停止しない。[Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)
