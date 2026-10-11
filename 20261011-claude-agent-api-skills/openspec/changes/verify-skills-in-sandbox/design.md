# Design

## Context

- このディレクトリには、OpenSpec の設定とメモ(`xprivate/`)しかない。コードは新しく作る。
- 参考にする既存プロジェクト:
  - `../20261010-claude-agent-sdk-sessionstore`: `claude-agent-sdk` 0.2.165、`ClaudeAgentOptions(model="claude-haiku-5-5", tools=[], mcp_servers=..., setting_sources=[], max_budget_usd=...)`、in-process MCP(`create_sdk_mcp_server`)、`typesafe-sdk` の `system_one` で noul を得る `jev.py`(閾値 0.3)。
  - `../20260922-claude-managed-agents`: `client.beta.environments.create(config={"type": "self_hosted"})`、`client.skills.create(files=files_from_dir(...))`、Agent の `skills` には `version` を渡さない(明示すると、ワーカーのダウンロードが `Invalid version id` で黙って失敗する)。ワーカーは `anthropic.lib.environments.EnvironmentWorker(workdir="/workspace")`。前回の観測では、スキルは `/workspace/skills/<name>/SKILL.md` にダウンロードされた。ただし haiku 4.5 は自分からはそこを見に行かなかった。
- Agent SDK の `ClaudeAgentOptions.skills`(`"all"` または名前のリスト)で、スキル機能を有効にする。スキルの探索元は、`cwd` 配下の `.claude/skills/`(project)。`sandbox` オプションはホスト上で bash を隔離する機能で、リモートでの実行には使えない。
- sandboxd(kubernetes-sigs/agent-sandbox、KEP-539.2): gRPC `:9090` で ProcessService(`Execute` は unary、`Start` はストリーム)、HTTP `:8080` で FilesystemService(`GET/PUT/DELETE /v1/files/{path}`、`GET /v1/health`)を提供する。`--root-dir`(既定 `/workspace`)の外にはアクセスできない。認証はない。コマンドは `/bin/sh -c` で実行され、呼び出しのあいだで状態は持ち越されない(`cd` は次の呼び出しに残らない)。
- `.env` にあるのは `CLAUDE_API_KEY` と `JEV_API_TOKEN`。

## Goals / Non-Goals

**Goals:**
- 「スキルのファイルはどこにあり、モデルはどのパスで読もうとし、スクリプトはどこで動くか」を、2 つの方式それぞれについて、tool 呼び出しの記録という一次情報で示す。
- 同じスキル `sandbox-probe` を両方の検証で使い、結果を比べられるようにする。

**Non-Goals:**
- GKE と Agent Sandbox のコントローラは使わない。ローカルの Docker だけで検証する。
- Managed Agents のワーカーを sandboxd の上で動かすことはしない。ワーカーのコンテナ自体をサンドボックスとみなす。
- セキュリティの強化(非 root 化、egress の制限)はしない。
- スキルのファイルをサンドボックスへ自動で同期する仕組みは作らない。条件 B では、検証コードが手動でコピーする。

## Decisions

### D1. sandboxd のイメージはソースからビルドする
Dockerfile をマルチステージにする。Go のステージで、agent-sandbox のリリースタグを固定して `sandboxd` をビルドし、`python:3.13-slim` に載せる。マーカーファイル `/etc/sandbox-marker` は、ビルド引数から作る。起動は `sandboxd --root-dir=/workspace` で、`-p 127.0.0.1:9090:9090 -p 127.0.0.1:8080:8080` とする。
- 代替案: 公開済みのイメージを使う。名前と内容が文書で確認できず、Python も入っているとは限らないため採用しない。実装時に公式イメージが見つかり、Python を足すだけで済むなら、それをベースにしてもよい。

### D2. Python クライアントは proto から gRPC スタブを生成する
ProcessService は、固定したタグの `.proto` から `grpcio-tools` でスタブを生成し、`Execute` を使う。FilesystemService は `httpx` で呼ぶ。小さなクライアントクラス(`exec(command) -> (exit_code, stdout, stderr)`、`read`、`write`、`list`)にまとめる。
- 代替案: `agentic-sandbox-client`。Kubernetes の Pod へのトンネルが前提で、ローカルの Docker には直接つなげないため採用しない。

### D3. Agent SDK では組み込みツールを無効にし、in-process MCP でサンドボックス用の tool を出す
`tools=[]`(条件 C だけ `["Read"]`)、`skills=["sandbox-probe"]` とし、`mcp_servers={"sandbox": ...}` で 3 つの tool を出す。
- `sandbox_exec(command)`: `sh -c` で実行し、終了コード・標準出力・標準エラーを返す
- `sandbox_read_file(path)`
- `sandbox_list_dir(path)`

`permission_mode="bypassPermissions"`、`setting_sources=["project"]`(スキルを見つけるため)とし、`CLAUDE_CONFIG_DIR` は実行ごとに一時ディレクトリにする。ホストで何かが実行されていないことは、`AssistantMessage` の `ToolUseBlock` をすべて記録して確認する。

### D4. パスの対応: ホストのプロジェクトディレクトリを、サンドボックスの `/workspace` に対応させる
ホスト側は実行ごとに一時ディレクトリ `<tmp>/project` を作り、`cwd` にする。その中に `.claude/skills/sandbox-probe` を置く。Skill tool が示すベースディレクトリは、ホストのパス(`<tmp>/project/.claude/skills/...`)になる見込みである。一方、sandboxd は `/workspace` の外を触れない。そこで、サンドボックス用の tool は、引数やコマンド文字列に含まれる `<tmp>/project` を `/workspace` に置き換えてから sandboxd に渡す。置き換え前の生の値も記録する。
- 条件 A: サンドボックスには何もコピーしない。パスの置き換えは行う。失敗するなら、原因は「ファイルが無いこと」だけになる。
- 条件 B: 実行前に、スキルのディレクトリを `/workspace/.claude/skills/sandbox-probe` に PUT する(スクリプトは mode を指定して実行権限を付ける)。
- 条件 C: コピーしない。参照ファイルはホストの Read で読める。スクリプトの実行はサンドボックスで行う。
- 代替案: コンテナにホストと同じ絶対パスを作る(bind mount)。sandboxd の `--root-dir` の制約と、GKE では成り立たないことから採用しない。置き換えの有無で結果が変わる可能性は、生の値の記録で追えるようにしておく。

### D5. 検証用スキル `sandbox-probe`
- `SKILL.md`: 「`reference.md` を読んで合言葉を得る」「`scripts/probe.py` を実行する」「合言葉とスクリプトの出力を、決まった形式で報告する」と指示する。パスは、スキルのディレクトリからの相対パスで書く(実際のスキルと同じ書き方にする)。
- `reference.md`: 合言葉。固定値(例 `KUMQUAT-7412`)とする。
- `scripts/probe.py`: `PROBE_HOST`、`PROBE_MARKER`(`/etc/sandbox-marker` の内容、無ければ `MISSING`)、`PROBE_CWD`、`PROBE_SCRIPT`(`__file__` の絶対パス)、`PROBE_PYTHON`(`sys.executable`)を出力する。標準ライブラリだけを使う。
- 同じディレクトリを、Agent SDK ではホストに置き、Managed Agents では Skills API に送る。

### D6. Managed Agents は、常駐ワーカーコンテナ 1 つで検証する
前回のモード A に相当する。`docker run -d` でワーカーを 1 つ起動し、`EnvironmentWorker.run()` でポーリングさせる。セッションごとのコンテナ(モード B)は、この検証の問い(スキルの配置と実行)に関係しないので扱わない。
- 準備(`provision.py`): Environment(self_hosted)→ Skill → Agent(`model="claude-haiku-5-5"`、`agent_toolset_20260401` から web_search と web_fetch を外す、`skills=[{"type": "custom", "skill_id": ...}]`)。ID は `.provisioned.json` に保存し、再実行しても重複して作らない。
- Environment key は人が Console で発行し、`.env` に `ANTHROPIC_ENVIRONMENT_ID` / `ANTHROPIC_ENVIRONMENT_KEY` として書く。`CLAUDE_API_KEY` はホストのドライバだけが使い、コンテナには渡さない。
- ドライバ(`run_managed.py`): セッションを作り、依頼を送り、idle になるまでイベントを受け取る。tool の呼び出しと結果、最終応答を `results/managed_*.json` に保存する。
- 依頼は 2 段階にする。①パスを示さない自然な依頼、②①でスキルが使われなかった場合、`/workspace/skills/sandbox-probe/` を明示した依頼。
- エージェントとは別に、`docker exec` でコンテナ内の `ls -laR /workspace/skills` を取り、ファイルの配置と権限を独立に確認する。

### D7. 判定と記録
- `jev.py` は sessionstore のものを流用し、閾値は 0.3 とする。質問は「値 X を述べているか」と「スクリプトの実行に失敗したと述べているか」の 2 種類。
- マーカーと合言葉は、文字列照合でも判定する。食い違いは `results/jev_summary.json` に保存する。
- テストは pytest にする。API を呼ぶテストには `live` マーカーを付ける。sandboxd クライアントとスクリプト単体のテストは、API を使わずに走る。
- `REPORT.md` には、結論の表(条件ごとに: スキルのパス / 参照ファイルの読み取り / スクリプトの実行場所 / 応答の判定)と、観測した tool 呼び出しの抜粋を書く。

## Risks / Trade-offs

- [sandboxd のビルド方法や proto の場所がタグによって違う] → タグを固定し、実装の最初のタスクでビルドとヘルスチェックまでを確認する。
- [`Execute` が cwd や env を受け取れない] → コマンドを `cd /workspace && ...` の形で包む(sandboxd は `sh -c` で実行する)。
- [haiku 5.5 がスキルを使わない、または自由に答えて形式が崩れる] → 結果はそのまま観測として記録する。形式の崩れは Jev で吸収する。Managed Agents では、パスを示した依頼で再試行する。
- [D4 のパスの置き換えが、現実の構成と違う挙動を生む] → 置き換え前のパスを記録し、報告書で「置き換えありの結果」であることを明記する。
- [API の費用] → `max_budget_usd`(1 回 0.2 USD)と `max_turns` を設定する。Managed Agents のセッションは、検証が終わったら idle のまま放置せずに終了させる。
- [Environment key の発行が手作業] → README の準備手順に書き、キーが無いときは Managed Agents の live テストを skip する。

## Migration Plan

新しい検証プロジェクトなので、移行はない。片付けは README の手順(Agent の archive は取り消せないので手動、Skill の delete、Environment の archive、Docker のコンテナとイメージの削除)で行う。

## Open Questions

- Agent SDK の Skill tool が返す内容に、ベースディレクトリの絶対パスが含まれるかどうか。これは検証で観測する対象であり、どちらの結果でも、計画とタスクは変わらない。
