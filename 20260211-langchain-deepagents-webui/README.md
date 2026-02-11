# DeepAgent WebUI

langchain-deepagent を使った AI エージェントの WebSocket サーバーと React WebUI です。

## 必要な環境

- Python 3.13+
- Node.js 18+
- TAVILY_API_KEY (環境変数)

## セットアップ

### サーバー側

1. Python 依存関係のインストール:
```bash
uv sync
```

2. 環境変数の設定:
`.env` ファイルに以下を設定してください:
```
TAVILY_API_KEY=your_api_key_here
```

### クライアント側

1. クライアントディレクトリに移動:
```bash
cd client
```

2. 依存関係のインストール:
```bash
npm install
```

## 起動方法

### サーバーの起動

プロジェクトルートディレクトリで:
```bash
uv run python -m server.server
```

サーバーは `http://localhost:8000` で起動します。
WebSocket エンドポイント: `ws://localhost:8000/ws`

### クライアントの起動

別のターミナルで、`client` ディレクトリから:
```bash
npm run dev
```

WebUI は `http://localhost:3000` で起動します。

## 使い方

1. サーバーとクライアントの両方を起動
2. ブラウザで `http://localhost:3000` を開く
3. 接続が確立されると「接続中」と表示される
4. メッセージ入力欄にテキストを入力して送信
5. AI エージェントが応答を返す

## 機能

- WebSocket によるリアルタイム通信
- AI エージェントとの日本語対話
- インターネット検索機能（internet_search ツール）
- レスポンシブデザイン

## 技術スタック

### サーバー
- Python 3.13
- FastAPI
- langchain-deepagents
- Tavily API (Web検索)
- Google Gemini 2.5 Flash

### クライアント
- React 18
- TypeScript
- Vite
- WebSocket API
