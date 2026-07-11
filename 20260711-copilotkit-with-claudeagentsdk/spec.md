# CopilotKit × Claude Agent SDK 対話UI 検証仕様

## 1. 目的

Claude Agent SDKをバックエンドのエージェント実行基盤として使用し、CopilotKitで実用的なWeb対話UIを構築できるか検証する。

今回のPoCでは、次の問いに明確な合否を出す。

1. Claudeの応答を生成途中からストリーミング表示できるか。
2. 会話履歴と作業状態を永続化し、プロセスやブラウザを閉じた後も再開できるか。
3. ユーザーが複数のセッションを作成・一覧表示・切り替えできるか。
4. Claude Agent SDKのtool callをCopilotKit UIへ正しく伝達できるか。
5. Claude Agent SDKとCopilotKitの間を、将来ライブラリとして再利用可能な境界に分離できるか。

## 2. 検証対象

### 対象に含めるもの

- Next.js + CopilotKitによるチャットWeb UI
- Claude Agent SDK + Vertex AIによる応答生成
- AG-UI互換のSSEストリーミングエンドポイント
- テキスト、tool call、tool result、実行状態のイベント変換
- SQLiteを使ったローカル永続化
- 複数スレッドの作成、一覧、切り替え、再開
- エラー、切断、再読み込み時の最低限の回復動作
- 自動テストと手動E2E確認

### 初回PoCでは対象外

- マルチユーザー認証と権限管理
- PostgreSQLなどを用いた本番スケール構成
- 複数サーバー間の排他制御
- ファイル添付、画像、音声
- CopilotKitのGenerative UI
- 人間によるtool実行承認
- セッション共有、検索、エクスポート

## 3. 想定アーキテクチャ

```text
Browser
  └─ Next.js / CopilotKit UI
       └─ CopilotKit Runtime
            └─ AG-UI (HTTP POST + SSE)
                 └─ Claude Agent SDK adapter (Python)
                      ├─ Claude Agent SDK
                      │    └─ Vertex AI / Claude Haiku 4.5
                      ├─ application tools
                      └─ SQLite session repository
```

Claude Agent SDKを直接React UIへ接続せず、Python側にAG-UIアダプターを置く。アダプターはClaude Agent SDKのメッセージを次のAG-UIイベントへ変換する。

| Claude Agent SDK | AG-UI |
| --- | --- |
| 実行開始 | `RUN_STARTED` |
| Assistantのテキスト差分 | `TEXT_MESSAGE_START/CONTENT/END` |
| `ToolUseBlock` | `TOOL_CALL_START/ARGS/END` |
| tool実行結果 | `TOOL_CALL_RESULT` |
| 状態全体または差分 | `STATE_SNAPSHOT` / `STATE_DELTA` |
| 正常終了 | `RUN_FINISHED` |
| 例外 | `RUN_ERROR` |

専用のClaude Agent SDKアダプターが利用可能になった場合でも、UIと保存層を変更せずアダプターだけ差し替えられる構造を目指す。

## 4. 機能要件と合格条件

### F-01 テキストストリーミング

ユーザーがメッセージを送信すると、Claudeの回答が完了する前から画面に逐次表示されること。

合格条件:

- 最初のテキスト断片が応答完了前に表示される。
- 2つ以上のテキスト差分イベントをUIが受信する。
- 画面上で同一回答が重複しない。
- 日本語と改行が崩れない。
- 完了時の表示内容が、保存されたassistantメッセージと一致する。
- 生成中は送信中または実行中の表示が出る。

計測項目:

- 送信から`RUN_STARTED`までの時間
- 送信から最初のテキスト表示までの時間（TTFT）
- 送信から`RUN_FINISHED`までの時間
- 1応答あたりのテキスト差分イベント数

### F-02 tool callの表示

既存のダミー天気toolを呼び出す質問を送信し、toolの実行過程と結果をUIに伝達できること。

合格条件:

- `get_today_weather`のtool call開始、引数、完了、結果をイベントとして受信する。
- tool handlerが1回だけ実行される。
- UIに少なくとも「ツール実行中」とツール名が表示される。
- 最終回答にダミー値`25℃`が含まれる。
- tool resultが通常のユーザーメッセージとして誤表示されない。
- リロード後もtool callと結果の履歴を復元できる。

### F-03 セッション状態の保存と再開

`threadId`単位で会話履歴とエージェントの作業状態を保存する。

保存対象:

- thread ID
- タイトル
- 作成日時、更新日時
- user/assistantメッセージ
- tool callとtool result
- Claude Agent SDKの再開に必要なsession ID
- アプリケーション固有state
- 最後のrun状態（idle/running/completed/error/interrupted）

合格条件:

- 2ターン以上会話した後、ブラウザをリロードして同じ履歴が表示される。
- PythonとNext.jsの両プロセスを再起動しても履歴を復元できる。
- 再開後の質問で、Claudeが以前の会話内容を参照できる。
- 保存済みのtool call/resultも復元される。
- 保存失敗時に、成功したようにUI表示しない。
- 不完全なrunが残っている場合は、再実行するのではなく`interrupted`として扱う。

検証では以下を分けて確認する。

1. UI履歴の復元: 保存済みメッセージが画面に戻ること。
2. エージェント文脈の復元: Claude自身が過去の文脈を使えること。
3. アプリ状態の復元: AG-UI stateが画面とバックエンドで一致すること。

### F-04 複数セッション

ユーザーが複数の独立した会話を保持し、任意に切り替えられること。

必要なUI:

- 「新しいセッション」ボタン
- セッション一覧
- 現在選択中のセッション表示
- セッションタイトル
- 最終更新日時

合格条件:

- 新規作成ごとに一意な`threadId`が発行される。
- セッションAとBで履歴とエージェント状態が混ざらない。
- A→B→Aと切り替えたとき、Aの履歴と状態が復元される。
- 切り替え後の送信先が、選択中の`threadId`になる。
- ブラウザリロード後もセッション一覧と最後に選択したセッションを復元できる。
- 更新日時の降順で一覧表示できる。
- 生成中のセッションから別セッションへ切り替えた場合も、イベントが別スレッドへ混入しない。

### F-05 エラーと切断

合格条件:

- Vertex AIエラーをチャット本文とは別のエラー状態として表示する。
- SSE切断時にUIが永久に「生成中」にならない。
- 同じ送信操作が二重実行されない。
- エラー後に同じセッションで再送信できる。
- ブラウザ切断後も、確定済みメッセージを失わない。

### F-06 キャンセル

PoCで実装可能性を調査し、可能なら生成停止ボタンを提供する。

合格条件:

- 停止操作後、新しいテキスト差分が表示されない。
- バックエンドのClaude実行も中断される。
- runを`interrupted`として保存する。
- 停止後も同じセッションで次の質問を送信できる。

キャンセルがClaude Agent SDKまたはCopilotKitの制約で実装できない場合は、不合格ではなく制約と代替策を記録する。

## 5. 永続化モデル案

### threads

| 列 | 用途 |
| --- | --- |
| `id` | CopilotKit/AG-UIのthread ID |
| `title` | 一覧表示名 |
| `agent_session_id` | Claude Agent SDKの再開用ID |
| `state_json` | アプリケーション/エージェント状態 |
| `last_run_status` | 最後のrun状態 |
| `created_at` | 作成日時 |
| `updated_at` | 更新日時 |

### messages

| 列 | 用途 |
| --- | --- |
| `id` | メッセージまたはイベントID |
| `thread_id` | 所属thread |
| `role` | user/assistant/tool/system |
| `content_json` | テキスト、tool call、tool result |
| `sequence` | thread内の順序 |
| `created_at` | 作成日時 |

ストリーム中の細かいテキスト差分をすべてDBへ保存する必要はない。run完了時に確定メッセージとして保存し、途中切断に対応する場合だけ一定間隔でドラフトをcheckpointする。

## 6. セッション再開方式の比較

次の2方式を検証し、採用方式を決める。

### A. Claude Agent SDKのsession resumeを利用

- Claude側のセッションIDをthreadに保存する。
- 再開時に同じClaudeセッションをresumeする。
- 長所: Claude Agent SDK本来のコンテキストを維持しやすい。
- 確認事項: プロセス再起動後の有効性、保存期間、Vertex AI利用時の挙動、SDKバージョン間互換性。

### B. 保存メッセージから新しいClaudeセッションを再構築

- DBの履歴をプロンプトまたはSDKメッセージとして再投入する。
- 長所: アプリ側が履歴の正本になり、移行しやすい。
- 確認事項: トークン増加、tool履歴の再構築、長い会話の要約方式。

PoCではAを第一候補とし、再開不能時のフォールバックとしてBの成立性も記録する。

## 7. API境界案

最低限、次の操作をUIへ提供する。

| 操作 | 役割 |
| --- | --- |
| `POST /agent/run` | AG-UI入力を受け、SSEイベントを返す |
| `GET /threads` | セッション一覧取得 |
| `POST /threads` | 新規セッション作成 |
| `GET /threads/{id}` | 履歴とstate取得 |
| `PATCH /threads/{id}` | タイトルなどの更新 |

削除は初回PoCの必須要件にしない。

## 8. 非機能要件

### セキュリティ

- Service Account JSONをブラウザやNext.jsクライアントへ渡さない。
- Vertex AI認証とClaude Agent SDK実行はPythonバックエンド内に限定する。
- `.env`とcredential JSONをGit管理しない。
- ログへ認証情報やプロンプト全文を不用意に出さない。
- `threadId`だけで他ユーザーの履歴を参照できる設計を本番採用しない。

### 整合性

- threadごとに同時runを1つまでに制限する。
- 各イベントに`threadId`と`runId`を付ける。
- 同じrun/eventを再受信しても重複保存しない。
- DB更新はメッセージとthread更新を可能な範囲でトランザクション化する。

### 観測性

最低限、以下を構造化ログへ出す。

- thread ID
- run ID
- Claude session ID
- 使用モデル
- run開始・終了・エラー
- tool名と所要時間
- TTFTと総応答時間
- 入出力トークン数（SDKから取得可能な場合）

## 9. テスト計画

### 自動テスト

1. Claude SDKメッセージからAG-UIイベントへの変換単体テスト
2. テキスト差分の順序と連結結果のテスト
3. tool call/result変換テスト
4. thread repositoryのCRUDテスト
5. thread A/B間のデータ分離テスト
6. プロセス再起動を模したDB再読み込みテスト
7. SSEエンドポイントのイベント順序テスト
8. Vertex AIを使う既存の有料統合テスト

### 手動E2Eシナリオ

1. 新規セッションAを作る。
2. 長めの回答を求め、ストリーミングを目視確認する。
3. 東京の天気を聞き、tool callと`25℃`を確認する。
4. Claudeに覚えておく値を伝える。
5. セッションBを作り、Aの内容が混ざらないことを確認する。
6. Aへ戻り、履歴と記憶した値を確認する。
7. ブラウザをリロードし、同じ状態が戻ることを確認する。
8. Next.jsとPythonを再起動し、再度Aを開いて会話を継続する。
9. 応答中に別セッションへ切り替え、イベント混入がないことを確認する。
10. バックエンド停止などでSSEを切断し、エラー回復を確認する。

## 10. PoC完了条件

以下をすべて満たせば、「CopilotKitでClaude Agent SDKの対話UIを構築可能」と判断する。

- F-01からF-05の合格条件を満たす。
- Claude Agent SDKとUIの間がAG-UIアダプターとして独立している。
- 複数threadを切り替えても履歴・state・イベントが混ざらない。
- プロセス再起動後も過去の作業を再開できる。
- 手動E2Eシナリオの結果を記録できる。
- 起動手順がREADMEだけで再現できる。

F-06のキャンセルは、制約が明文化されていればPoC完了の必須条件にはしない。

## 11. 実装順序

1. Claude Agent SDK → AG-UIイベント変換の最小アダプター
2. CopilotKitチャットでテキストストリーミング
3. 天気tool callのイベント表示
4. SQLiteによる単一threadの保存と再開
5. thread一覧、新規作成、切り替え
6. エラー、切断、同時run対策
7. 自動テストとE2E結果の記録
8. 再利用部分をPythonパッケージとして切り出す判断

## 12. 未決事項

- Next.jsのCopilotKit Runtimeを必須とするか、Python AG-UI endpointへ直接接続するか。
- Claude Agent SDKのsession resumeを履歴の正本にできるか。
- CopilotKit側のthread persistence機能をどこまで使い、独自DBとどう責務分担するか。
- tool callを標準表示だけにするか、専用Reactコンポーネントで表示するか。
- 応答中のthread切り替え時に、バックグラウンド継続・キャンセルのどちらを採用するか。
- ライブラリ化の対象をAG-UI変換だけにするか、保存層のinterfaceまで含めるか。

## 13. 参考資料

- [CopilotKit: AG-UI](https://docs.copilotkit.ai/ag-ui)
- [CopilotKit: AG-UI protocol and events](https://docs.copilotkit.ai/langgraph-python/ag-ui)
- [CopilotKit: CopilotChat](https://docs.copilotkit.ai/reference/v2/components/CopilotChat)
- [CopilotKit: loading message history and switching threads](https://docs.copilotkit.ai/crewai-crews/persistence/loading-message-history)
- [CopilotKit: loading agent state](https://docs.copilotkit.ai/crewai-crews/persistence/loading-agent-state)
- [Claude Agent SDK for Python](https://github.com/anthropics/claude-agent-sdk-python)
