# self-hosted セッションのエージェント設定

## 配置と設定の対応

| 設定対象 | 配置または API パラメータ | 読み込む主体 |
| --- | --- | --- |
| プロジェクト規約 | `/workspace/AGENTS.md` | セッションの Codex harness |
| skill とローカル MCP | `/workspace/capabilities/plugins/<plugin>/` | セッションの Codex harness |
| プラグインの公開 | `environment.capability_directories` にプラグインのルートを列挙 | Agents API |
| エージェント全体の方針 | `agent.instructions` | Agents API |
| executor 接続 | `codex exec-server --remote … --environment-id …` | コンテナ |

このリポジトリの `.agents/skills/` はホスト側の Codex 用です。Dockerfile はそこを
`/workspace` へコピーもマウントもしていないため、self-hosted executor からは見えません。
executor 用に使う skill は `capabilities/plugins/` 以下へ置き、イメージへ含めます。

## 推奨レイアウト

```
/workspace/
├── AGENTS.md
└── capabilities/
    └── plugins/
        └── <plugin-name>/
            ├── .codex-plugin/plugin.json
            ├── .mcp.json                 # MCP を使う場合
            └── skills/<skill-name>/SKILL.md
```

`capability_directories` には `<plugin-name>` の絶対パスを一つずつ指定します。親ディレクトリは
skill を発見できますが、子プラグインごとの MCP 設定は読み込みません。

## セッション作成時の設定例

```python
client.beta.agents.sessions.create(
    agent={
        "model": "gpt-5.6-luna",
        "instructions": "日本語で簡潔に回答し、必要なときは $configuration-probe を使う。",
    },
    environment={
        "type": "self_hosted",
        "workspace_directory": "/workspace",
        "capability_directories": [
            "/workspace/capabilities/plugins/config-probe",
        ],
    },
)
```

`agent.instructions` はセッションの方針を置く場所です。`AGENTS.md` にはリポジトリ固有の
作業規約、skill には特定作業の手順を置きます。設定を変更した場合は新しいセッションを作ります。

## MCP の選択

コンテナで起動するローカル MCP はプラグインの `.mcp.json` に定義します。必要な実行ファイルと
依存ライブラリは Docker イメージへ含め、シークレットは環境変数として実行時に渡します。

OpenAI 側から利用する HTTP MCP は、プラグインではなく `agent.tools` にも直接定義できます。
どちらを使うかは、MCP サーバーをコンテナで実行するか、ネットワーク上の HTTP サーバーとして
提供するかで決めます。

`codex exec-server` の `--config` やコンテナ内 `~/.codex/config.toml` は executor 自身の設定です。
Agents API の skill・ローカル MCP をセッションへ公開する設定としては使用しません。

## 同梱した確認用プラグイン

`config-probe` は次の 3 層を確認するための小さな fixture です。

- `AGENTS.md`: `AGENTS_PROBE=jade-lantern`
- skill: `SKILL_PROBE=amber-orbit`
- MCP: `openai_docs` を呼んだ後に `MCP_PROBE=used`

イメージを再ビルド後、上記プラグインを `capability_directories` に指定した新規セッションへ、
「configuration-probe を使い、OpenAI Docs MCP を確認して」と入力して検証します。

## 実 API での確認結果（2026-09-22）

`gpt-5.6-luna` の新規 self-hosted セッションで確認した。ターンは
`agent.session.turn.completed` となり、保存された session items に `mcp_call` が含まれた。
回答には `AGENTS_PROBE=jade-lantern`、`SKILL_PROBE=amber-orbit`、`MCP_PROBE=used` の
3 行が含まれた。これにより、イメージ内の `/workspace/AGENTS.md`、
`capability_directories` で指定した skill、プラグインの `.mcp.json` が同じ
self-hosted セッションで使われることを確認した。

比較として、同じイメージで `capability_directories` を省略した別の新規セッションも作成した。
そのセッションは `configuration-probe` と `openai_docs` を利用不可と回答し、
items に `openai_docs` の呼び出しは存在しなかった。プラグインを指定したセッションには
`server_label: openai_docs`、`name: search_openai_docs`、`status: completed` の MCP call が
記録されている。なお、両セッションには harness 自身の環境確認用 `codex` MCP が存在する。
