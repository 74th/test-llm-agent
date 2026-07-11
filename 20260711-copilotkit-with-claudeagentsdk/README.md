# Claude Agent SDK + Vertex AI spike

Claude Agent SDKをGoogle Vertex AI経由で起動し、Pythonプロセス内のダミー天気toolを呼べるか検証する最小構成です。

## Setup

```bash
uv sync --dev
gcloud auth application-default login
```

Vertex AI側でAnthropic APIを有効化し、利用するClaudeモデルへのアクセスも有効にしてください。

## Tests

課金やクラウド認証を伴わない単体テスト:

```bash
uv run pytest -m "not vertex"
```

Vertex AIを実際に呼ぶ統合テスト（API利用料が発生します）:

```bash
export CLAUDE_CODE_USE_VERTEX=1
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id"
export CLOUD_ML_REGION="global"
# 必要な場合のみ、Vertex AIで利用可能なモデルIDを指定
# export ANTHROPIC_MODEL="claude-sonnet-4-5@20250929"
RUN_VERTEX_INTEGRATION=1 uv run pytest -m vertex -v
```

統合テストは、SDKが返すtool-useブロックだけでなく、Python側のtool handlerが実際に1回実行され、最終回答にダミー値 `25℃` が含まれることまで確認します。
