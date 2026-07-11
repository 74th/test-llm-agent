# CopilotKit × Claude Agent SDK PoC

`spec.md` の検証用実装です。Next.js/CopilotKit Runtime から AG-UI (POST + SSE) を介して Python の Claude Agent SDK を呼び、SQLite に複数セッションの履歴と Claude session ID を保存します。天気質問ではプロセス内の `get_today_weather` が固定値 `25℃` を返します。

## 構成

- `poc/adapter.py`: Claude SDK メッセージから AG-UI イベントへの独立変換層
- `poc/repository.py`: SQLite thread/message repository
- `poc/app.py`: thread CRUD と `/agent/run` SSE API
- `web/`: Next.js、CopilotKit Runtime、複数セッション UI
- `tests/`: 変換、CRUD、セッション分離、再起動、SSE 順序テスト

## セットアップ

```bash
uv sync --all-groups
cd web && npm install && cd ..
cp .env.example .env
```

`.env` の Vertex AI project、region、model と認証情報を設定してください。credential JSON と `.env` は Git 管理対象外です。

## 起動

ターミナルを2つ使います。

```bash
# Python / AG-UI backend (http://localhost:8000)
uv run python main.py
```

```bash
# Next.js / CopilotKit UI (http://localhost:3000)
cd web
npm run dev
```

必要なら `AGENT_URL`（Next.js サーバーから Python へ接続する URL）、`NEXT_PUBLIC_AGENT_URL`（ブラウザから thread API へ接続する URL）、`POC_DATABASE` を指定できます。

## テスト

```bash
uv run pytest -m "not vertex"
cd web && npm run typecheck && npm run build
```

実課金の Vertex AI 統合テスト:

```bash
RUN_VERTEX_INTEGRATION=1 uv run pytest -m vertex -v
```

## 手動確認

1. 新規セッションで長めの質問を送り、複数のテキスト差分と実行中表示を確認する。
2. 「東京の天気」を聞き、tool 表示、結果、最終回答の `25℃` を確認する。
3. 2つのセッションを A → B → A と切り替え、履歴が混ざらないことを確認する。
4. ブラウザ、Next.js、Python を再起動し、一覧・履歴・継続文脈を確認する。
5. 応答中に「停止」または別セッションへ切り替え、`interrupted` になることを確認する。

## PoC上の制約

SQLite の履歴を UI の正本とし、Claude の継続文脈には SDK の `resume` を使います。SDK session resume が無効になった場合の履歴再投入フォールバックは未実装です。停止は CopilotKit/AG-UI の abort によってストリームを切断し、Python 側を `interrupted` にしますが、Vertex 側で既に処理中のリクエストが即時停止するかは SDK/transport に依存します。認証は対象外のため、この API をそのまま本番公開しないでください。
