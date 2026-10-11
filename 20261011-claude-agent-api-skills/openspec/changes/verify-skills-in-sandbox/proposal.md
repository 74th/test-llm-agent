# Proposal

## Why

コマンドを実行する tool call を、将来 GKE Agent Sandbox（sandboxd が動く Pod）の中で行う予定である。そのとき、スキル（`SKILL.md` と、スキル内の参照ファイル・Python スクリプト）がどこに置かれ、どこから読まれ、どこで実行されるのかが分かっていない。Claude Agent SDK と Claude Managed Agents（self-hosted environment）の両方について、GKE を使わずローカルの Docker で動きを確かめ、設計判断の材料にする。

## What Changes

- 検証用のスキル `sandbox-probe` を作る。`SKILL.md`、参照ファイル（合言葉が書かれた `reference.md`）、実行場所を報告する Python スクリプトを含む。
- **Claude Agent SDK の検証**: ローカルの Docker で sandboxd を起動する。組み込みの Bash / Read / Write などを無効にし、代わりに sandboxd を呼ぶカスタム tool（MCP）を用意する。そのうえで次を観測する。
  - スキルの `SKILL.md` がどこから読まれるか（ホスト側の Skill tool）
  - 参照ファイルと Python スクリプトがサンドボックス内のファイルとして扱われるか、別の経路があるか
  - スキルのファイルをサンドボックスへコピーしない場合とコピーする場合で、結果がどう変わるか
- **Claude Managed Agents の検証**: Skills API でスキルを事前登録し、Agent に添付する。self-hosted environment のワーカー（`EnvironmentWorker`）を Docker で起動する。スキルのファイルがコンテナのどこに置かれ、Python スクリプトがコンテナ内でどう実行されるかを観測する。
- エージェントの応答の判定に Jev（TypeSafe System One）を使う。応答の自然文が期待どおりの事実を述べているかを Jev で判定し、文字列の照合と併用する。
- 結果を `REPORT.md` にまとめる。モデルは両方とも `claude-haiku-5-5` を使う。

## Capabilities

### New Capabilities
- `sandboxd-local-runtime`: ローカルの Docker で sandboxd を起動し、プロセス実行とファイル操作を Python から呼べるようにする
- `agent-sdk-skill-sandbox`: Claude Agent SDK で、組み込みツールを sandboxd 経由のツールに置き換えたとき、スキルの読み込み・参照ファイル・スクリプト実行がどこで行われるかを検証する
- `managed-agent-skill-sandbox`: Claude Managed Agents で、Skills API に登録したスキルが self-hosted environment のコンテナにどう配置され、スクリプトがどう実行されるかを検証する
- `jev-response-judging`: エージェントの応答を Jev で判定し、テストの合否に使う

### Modified Capabilities
（なし）

## Impact

- 新しい Python プロジェクト（uv、Python 3.13）。依存: `claude-agent-sdk`、`anthropic`（Managed Agents と `EnvironmentWorker`）、`grpcio`（sandboxd の ProcessService）、`httpx`、`typesafe-sdk`、`python-dotenv`、`pytest`
- Docker イメージ 2 つ: sandboxd + Python（Agent SDK 用）と、self-hosted ワーカー（Managed Agents 用）
- Anthropic 側に作るリソース: self-hosted Environment、Skill、Agent。片付け手順を README に書く
- 秘密情報: `.env` の `CLAUDE_API_KEY` と `JEV_API_TOKEN`。Environment key は人が Console で発行する
- 参考にするプロジェクト: `../20261010-claude-agent-sdk-sessionstore`（Agent SDK と Jev）、`../20260922-claude-managed-agents`（self-hosted ワーカーとスキル登録）
