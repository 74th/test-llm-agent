# Tasks

## 1. セットアップ

- [x] 1.1 uv で Python 3.13 プロジェクトを作り、依存(claude-agent-sdk, typesafe-sdk, pytest, anyio, python-dotenv)を追加。`uv sync` が成功することを確認
- [x] 1.2 `.gitignore` に `.env` を追加し、`git status` で `.env` が追跡対象にならないことを確認
- [x] 1.3 `.env` 読み込みと設定モジュール(`CLAUDE_API_KEY` → `ANTHROPIC_API_KEY`、モデル `claude-haiku-5-5`)を実装。キー値を出力せず、Haiku への1往復のスモークテストが通ることを確認
- [x] 1.4 Jev ヘルパー(`typesafe-sdk` の `system_one`、`JEV_API_TOKEN` を `TYPESAFE_API_KEY` へ渡す)を実装し、疎通テストで noul の値が返ることを確認(キーが使えない場合はユーザへ報告)

## 2. SessionStore 検証

- [x] 2.1 `FileSessionStore`(`append`/`load`、`uuid` による重複排除)を実装し、`run_session_store_conformance` が通ることを確認
- [x] 2.2 `issue_token` MCP tool を実装し、「値を返答に書かない」指示で呼ばせたとき、最終返答に値が出ないことを確認するテストを書く
- [x] 2.3 `InMemorySessionStore` で、別 `CLAUDE_CONFIG_DIR` から resume して値を答えさせるテストを書き、応答に値が含まれることを確認
- [x] 2.4 `FileSessionStore` で新しいインスタンスから同じ検証を行い、成功することを確認
- [x] 2.5 `store.load` の内容に tool 結果の固有値が含まれることを直接 assert するテストを書き、成功することを確認
- [x] 2.6 サブエージェント経由の tool 結果が `subagents/...` の key に保存され、resume 後に参照できることをテスト(`tests/test_session_store_extra.py`)で確認
- [x] 2.7 `/compact` 後に境界・要約 entry が追記され、圧縮前の entry が残ることをテストで確認し、要約が値を保持するかを `results/compaction_finding.json` に記録

## 3. Jev による応答判定

- [x] 3.1 2.3/2.4 の応答を Jev(「値 X に言及しているか」)で判定するテストを書き、合格ケースが閾値以上になることを確認
- [x] 3.2 値に言及しない応答で不合格になる負例テストを書き、閾値未満になることを確認
- [x] 3.3 文字列一致との判定一致状況と `usage` のトークン数合計を集計して出力し、トークンが出力に含まれないことを確認

## 4. バックグラウンドタスク検証

- [x] 4.1 30〜60秒の `sleep` + 固有値出力をバックグラウンド実行させ、完了前に最初の ResultMessage が得られることを確認するテストを書く
- [x] 4.2 待機中に別プロンプトへの応答が得られるかを観測するテストを書き、結果(可/不可)を記録
- [x] 4.3 完了後に、新規入力なしで追加のアシスタント応答が来るかを観測するスクリプトを書き、メッセージ列を記録
- [x] 4.4 4.3 が不可の場合、完了を検知して完了通知を同一セッションへ resume 注入する代替方式を実装し、固有値に言及する応答が得られるか確認(Jev 判定併用)
- [x] 4.5 5分間のバックグラウンド処理で 4.1〜4.4 を1回だけ手動マーク付きテストとして実行し、結果を記録

## 5. 報告

- [x] 5.1 全テストを実行し、`REPORT.md` に各シナリオの成否、制約、コスト(トークン数)、Jev の所見を記載。`REPORT.md` と各 spec のシナリオが対応していることを確認
