# 検証レポート: Claude Agent SDK の SessionStore とバックグラウンドタスク

- 環境: Python 3.13 / `claude-agent-sdk` 0.2.165 / モデル `claude-haiku-5-5`(`src/verify/config.py` で指定、実行時も同名であることを確認)
- Jev: TypeSafe 公式 API(`typesafe-sdk` 0.7.4、`jev-latest`)。キーは `JEV_API_TOKEN`
- 再実行: `uv run pytest`(5 分テストは `uv run pytest -m slow`)

## 結論

| 検証項目 | 結果 |
| --- | --- |
| SessionStore を別実装に差し替えても resume できる | 可能(InMemory / 自作 FileSessionStore の両方で成功) |
| 返答に出ない tool 結果を、復元後の対話で参照できる | 可能(tool の再実行なしで参照) |
| バックグラウンド tool を起動して先に返答できる | 可能 |
| 待機中に次の対話を受け付けられる | 可能 |
| 完了を契機に追加応答できる | 可能(`ClaudeSDKClient` でも one-shot `query()` でも。5 分でも確認) |
| Jev で LLM 応答をユニットテスト判定できる | 可能。ただし厳格で、文字列一致の代替にはならない(補助向き) |

## 1. SessionStore(`tests/test_session_resume.py`、`tests/test_file_store.py`)

- 自作 `FileSessionStore`(JSONL、uuid で重複排除)は SDK 同梱の conformance テストを通過。
- 先行の対話: tool `issue_token` がランダム値(例 `TK-55340BFB`)を返すが、最終返答は「完了」のみ。値は返答に出ていない(アサート済み)。
- 復元: 新しいストアインスタンス + 別 `CLAUDE_CONFIG_DIR`(ローカル transcript なし)から `resume=session_id` で続きを質問 → 値を正しく回答。tool は再実行されず(発行は 1 回)。
- ストアの `load` の中に tool 結果の値が含まれることを直接確認。
- 対照実験: 空のストアから resume すると値を答えられない(復元がストアに依存している証拠)。
- Jev 判定: 復元後の応答は値を述べていると判定(>0.3)、先行の応答は述べていないと判定(≤0.3)。
- 注意(公式ドキュメントより): Python SDK は resume 時に認証情報と `.claude.json` しか引き継がない。`apiKeyHelper` 認証は使えないので、キーは環境変数で渡すこと。ミラー書き込みは best-effort のため、`append` は再送に備えて uuid で重複排除する。

### 1.1 サブエージェントとコンパクション(`tests/test_session_store_extra.py`)

- **サブエージェント**: 親から `worker` サブエージェントに tool を呼ばせると、transcript は `subagents/agent-<id>` の別 key で保存された(14 entries、tool 結果の値を含む)。自作ストアの `list_subkeys` で列挙できる。新しいストアインスタンス + 別 config dir からの resume で、値を参照できた(tool の再実行なし)。
  - 今回の worker は Agent tool 経由でバックグラウンド実行され、報告が親の transcript にも入るため、「サブエージェントの transcript だけにある情報」の復元は分離して確認していない。
- **コンパクション**: `/compact` 後、圧縮前の entry はすべて残り、`compact_boundary` と要約(`isCompactSummary`)の entry が追記された。**ただし要約は tool 結果の値を保持しなかった。** 圧縮後に resume して値を尋ねると、モデルは「会話に残っていない」と答えた(生のストアには値が残っている)。
  - 手動 `/compact` の動作で、おそらく Claude Code 本体の仕様どおり。圧縮後に追記されたのは、境界、要約 1 本、`/compact` 実行の注記だけで、直前の tool 呼び出し・結果もそのまま残さず、会話全体が要約に置き換わった。要約は「issue_token の依頼は完了、値は尋ねられるまで書かない規則」までは書いたが、値は含まなかった。手動コンパクションは次の作業に備えて意図的に捨てる操作なので、直前の結果が落ちるのは意図に沿う。
  - ストアは生の記録を持つが、復元時にモデルが見るのは圧縮後の連鎖。コンパクションが入り得る長いセッションでは、あとで参照させたい値は、tool 結果に頼らず返答や外部に書き出しておくと安全。
  - 自動コンパクション(直近を残して古い部分だけ要約するか)は未検証。長い会話が必要で費用がかかるため、対象外とした。発動しきい値を下げる環境変数(`CLAUDE_CODE_AUTO_COMPACT_WINDOW`、`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`)を試したが、設定した窓(25,000)を超える約 27.8k トークンまで育てても発動しなかった(この SDK 経由の実行では効いていない様子。理由は未調査。試行 4 回の費用は約 $0.2)。
- 途中でプロセスが落ちた場合は、対象外とした(ミラーは best-effort で、その実行中の書き損じは復元されない可能性がある)。

## 2. バックグラウンドタスク(`tests/test_background.py`)

値は実行時に計算される(`R$((n*3))`)ので、先行返答には現れない。

| 観測 | 結果 |
| --- | --- |
| 40 秒の処理 → 先行返答 | 約 4.6 秒 |
| 待機中の別質問への応答 | 約 4.9 秒 |
| 完了を契機とした追加応答 | 約 46 秒(完了直後)。`ResultMessage.origin.kind == "task-notification"`、応答に値を含む |
| one-shot `query()` | 2 つ目の result が同じイテレータに届く |
| 300 秒の処理(`-m slow`) | 先行返答後、307 秒で追加応答が届く |

- 追加応答は、ユーザの新規入力なしで SDK が自動起動したターン。`origin` で人間の入力と区別できる。
- 制約: 完了前にクライアントを閉じる(CLI プロセスが終了する)と、バックグラウンド処理も停止する(`stopped`)。resume しても通知は来ず、アプリ側から通知文を入力として注入しても、モデルは「完了を確認できない」と答えた。サーバ運用では、処理中は CLI プロセスを常駐させる必要がある。完了通知を別プロセスの SessionStore 経由で復元する運用は成立しない。
- 代替方式(完了通知を resume で注入)は、標準機能が動くため不要。上記のとおり、プロセスが消えた後の救済にもならない。

### 2.1 クライアント側の読み方と「次を送ってよいか」

- `receive_response()` は最初の `ResultMessage` で終わるので、追加応答を取り逃がす。`receive_messages()`(開いたまま読み続ける)を使う。one-shot `query()` はバックグラウンド処理を待って最後に閉じる。
- 「裏で走っているものがある」ことは、先行返答の前後に流れる `task_started` / `background_tasks_changed` の system メッセージで分かる。完了は `task_updated` / `task_notification`。SDK はポーリングしない。CLI が完了で新しいターンを始め、同じ接続に流す。
- 送信と受信は別々の asyncio タスクにできる(スレッドは不要)。`client.query()` は入力を書くだけで戻るので、受信タスクで `receive_messages()` を読み続けたまま、別タスクから追加指示を送れる(`scratch/probe_concurrent.py` で確認: 8 秒後に送った質問に約 2 秒で応答し、その後の完了通知の追加応答も届いた)。
- 次の入力を送ってはいけない状態はない。待機中に `client.query()` で別質問を送ると約 5 秒で答えが返り、その後に完了通知の追加応答も来た。
- 1 つの接続に、自分の入力へのターンと通知起動のターンが混ざる。`ResultMessage.origin`(`None` / `human` が自分の入力、`task-notification` が自動起動)で区別する。
- CLI は `session_state_changed`(`idle` / `running` / `requires_action`)を持ち、SDK 内部は実行終了の判断に使っている。ただし今回の検証では、クライアントが読むメッセージには現れなかった。「今アイドルか」は、`task_started` と `task_notification` / `task_updated` で実行中タスク数を数えて判断する想定になる。
- one-shot `query()` の待機は CLI 側の動作に依存し、SDK の既定上限は 10 分(`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`、既定 600,000ms)。10 分を超えるタスクは未検証。

## 3. Jev による判定(`tests/test_jev_vs_string.py`)

- 判定: noul が 0.3 より大きければ合格(ユーザ指定。`jev.THRESHOLD`)。
- 8 ケース: Jev 7/8、文字列一致 6/8(0.3 に下げたため、言い換え表現 0.59 も合格になる)。
- Jev は「小文字違い」を 0.05 と低く判定する(厳格)。言い換え表現は 0.59 と曖昧。
- 使用量: 入力 2,543 / 出力 160 トークン(`usage` にコストは含まれない)。
- 方針: 値の存在は文字列一致を主、Jev は「意味として述べているか」の補助判定に使うのが適切。

## 4. 前提の変更点

- Jev は OpenRouter ではなく、TypeSafe 公式の API(`https://api.typesafe.ai/v1/systemone`)。OpenRouter 前提だった design / specs / tasks はその旨に更新済み。

## 5. 再現時の注意

- 実行には少額の API 課金が発生する(Haiku、Jev)。
- キーは `.env`(git 管理外)。ログ・結果ファイルにキーが出ていないことを確認済み。
- `results/` に JSON を出力する(git 管理外)。
