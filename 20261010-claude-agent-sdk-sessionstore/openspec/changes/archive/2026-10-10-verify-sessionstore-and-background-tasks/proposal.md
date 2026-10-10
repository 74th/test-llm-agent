# Proposal

## Why

Claude Agent SDK でセッションを自前の SessionStore に載せ替えても、会話の継続が壊れないかを確認したい。特に「tool コールの結果がセッションに残るが、ユーザへの返答テキストには出ない」ケースで、続きの対話が復元されたセッション経由でその結果を参照できるかが不明である。また Claude Code のように「バックグラウンドでツールを走らせたまま一旦返答し、完了を契機に追加応答する」挙動が SDK で再現できるかも不明である。これらは SDK をサーバ運用する際の設計判断に直結する。

## What Changes

- 検証用 Python プロジェクトを新規に作る(`claude-agent-sdk`、`pytest`、`typesafe-sdk` 等)。
- 検証1: 標準の `InMemorySessionStore` と、自作の `SessionStore`(ファイル/SQLite 等、`append`/`load` を実装)で、tool コール結果が返答に出ないセッションを作り、ストアから `resume` した続きの対話で結果を参照できるか確認する。自作ストアは SDK 同梱の conformance テストも通す。
- 検証2: バックグラウンド実行したツール(数十秒〜数分)の完了を契機に、追加の応答を得られるか確認する。待ち時間中に別の対話を受け付けられるかも見る。
- 応答の合否判定に Jev(TypeSafe 公式の System One API、`jev-latest`)を使い、LLM 応答を pytest のユニットテストとして判定できるか試す。
- 利用モデルは安価な `claude-haiku-5-5`。API キーは `.env` の `CLAUDE_API_KEY`(SDK には `ANTHROPIC_API_KEY` として渡す)、Jev は `JEV_API_TOKEN`(Jev 公式サイトのキー)。
- 本番コードの変更はなし。成果物は検証コードと結果レポート。

## Capabilities

### New Capabilities
- `session-store-resume`: カスタム SessionStore へ保存したセッションを resume し、前回の tool 結果を参照できることの検証。
- `background-task-continuation`: バックグラウンド tool の完了を契機とした追加応答が SDK で可能かの検証。
- `jev-response-judging`: Jev を判定器とした LLM 応答のユニットテスト手法の検証。

### Modified Capabilities

(なし。既存 spec は空)

## Impact

- 新規: `pyproject.toml`、`src/` の検証コード、`tests/`、`REPORT.md`。
- 依存: `claude-agent-sdk`、`pytest`、`pytest-asyncio`(または anyio)、`typesafe-sdk`、`python-dotenv`。
- 外部サービス: Anthropic API(Haiku 5.5)と TypeSafe(Jev)。いずれも少額の従量課金が発生する。
- `.env` は秘密情報なので git 管理に含めない。
