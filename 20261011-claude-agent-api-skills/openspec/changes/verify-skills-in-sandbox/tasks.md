# Tasks

## 1. プロジェクトの準備

- [x] 1.1 `uv init` で Python 3.13 のプロジェクトを作る(`src/verify/`、`tests/`、`results/`)。依存(`claude-agent-sdk`、`anthropic`、`grpcio`、`grpcio-tools`、`httpx`、`typesafe-sdk`、`python-dotenv`、`pytest`、`anyio`)を追加する。pytest の `live` マーカーと `pythonpath=["src"]` を設定する。`.gitignore` に `.env`、`.provisioned.json`、`results/`、生成した gRPC スタブ以外の一時物を入れる。`uv run pytest --collect-only` が通ることで確認する
- [x] 1.2 `src/verify/config.py` を作る。`.env` を読み込み、モデル `claude-haiku-5-5`、`CLAUDE_API_KEY`、`JEV_API_TOKEN`、Environment ID / key を返す。キーの値は出力しない。キーが欠けたときにエラーになる単体テストで確認する
- [x] 1.3 `src/verify/jev.py` を sessionstore から流用する(`noul`、`mentions_value`、`says_failed`、閾値 0.3、usage の記録)。合言葉を含む文と含まない文の 2 件で判定が分かれる live テストで確認する

## 2. 検証用スキル `sandbox-probe`

- [x] 2.1 `skills/sandbox-probe/` に `SKILL.md`、`reference.md`(合言葉)、`scripts/probe.py` を作る(design D5)。SKILL.md の本文に合言葉とマーカーが含まれていないことを、テストで確認する
- [x] 2.2 ホストで `python3 skills/sandbox-probe/scripts/probe.py` を実行し、`PROBE_MARKER: MISSING` を含む 5 行が出ることを確認する

## 3. sandboxd をローカルの Docker で動かす

- [x] 3.1 `docker/sandboxd/Dockerfile` を作る(Go のステージで agent-sandbox の固定タグから `sandboxd` をビルドし、`python:3.13-slim` に載せる。`/etc/sandbox-marker` も作る)。`docker build` が成功し、コンテナ内で `sandboxd --help` が動くことで確認する
- [x] 3.2 起動・停止のスクリプト `scripts/sandboxd_up.sh` / `sandboxd_down.sh` を作る(`127.0.0.1` だけに公開、`--root-dir=/workspace`)。`curl 127.0.0.1:8080/v1/health` が正常を返し、`docker port` の公開先が `127.0.0.1` だけであることで確認する
- [x] 3.3 同じタグの `.proto` から ProcessService のスタブを生成するスクリプトを作り、生成物を `src/verify/sandboxd_pb/` に置く。import できることで確認する
- [x] 3.4 `src/verify/sandboxd.py` に、クライアント(`exec`、`read`、`write(mode=...)`、`list`)を実装する。失敗は例外にせず、結果として返す。`tests/test_sandboxd.py` で、`python3 -c 'print(1+1)'` の出力が `2` になること、ファイルの往復、マーカーの読み取り、存在しないファイルと 0 以外の終了コードの扱いを確認する
- [x] 3.5 `probe.py` を sandboxd 経由でコンテナにコピーして実行し、`PROBE_MARKER` がビルド時の値になることを確認する(ホストとの区別ができることの確認)

## 4. Claude Agent SDK の検証

- [x] 4.1 `src/verify/sdk_agent.py` に、sandboxd を呼ぶ in-process MCP の tool(`sandbox_exec`、`sandbox_read_file`、`sandbox_list_dir`)を実装する。ホストのプロジェクトのパスを `/workspace` に置き換え、置き換え前と後の値を記録する(design D4)。tool の関数を直接呼ぶ単体テストで、パスの置き換えと記録を確認する
- [x] 4.2 同じファイルに、実行ヘルパーを実装する。一時プロジェクトを作ってスキルを置き、条件 A / B / C ごとに `ClaudeAgentOptions` を組み立てて実行する。実行結果として、ToolUseBlock / ToolResultBlock の全件、Skill tool の結果、最終応答、使われたモデル、費用を返す。条件 B では、実行前にスキルを `/workspace/.claude/skills/sandbox-probe` にコピーする。スキルを使わない短い依頼で動き、モデル名が `claude-haiku-5-5` になることを live テストで確認する
- [x] 4.3 `tests/test_sdk_skills.py`(live)で、条件 A / B / C を実行し、`results/sdk_<条件>.json` に保存する。どの条件でも、組み込みの Bash / Write / Edit / Glob / Grep が呼ばれていないこと(条件 C の Read だけは許す)をアサートする
- [x] 4.4 条件 B で、スクリプトの出力にサンドボックスのマーカーが含まれること、応答が合言葉とマーカーを述べていることを、文字列照合と Jev の両方で確認する。条件 A と C は、合否ではなく観測として記録する(参照ファイルとスクリプトそれぞれの成否、モデルが使ったパス)。Jev で「実行に失敗したと述べているか」も判定する

## 5. Claude Managed Agents の検証

- [x] 5.1 `docker/worker/Dockerfile` と `src/verify/worker_main.py` を作る(`python:3.13-slim`、`anthropic`、`/etc/sandbox-marker`、`EnvironmentWorker(workdir="/workspace").run()`)。`docker build` が成功することで確認する
- [x] 5.2 `scripts/provision.py` を作る。Environment(self_hosted)、Skill(`files_from_dir`)、Agent(`claude-haiku-5-5`、web 系の tool を外す、skills は `version` を指定しない)を作成または再利用し、`.provisioned.json` に ID だけを保存する。2 回実行しても、リソースが増えずに Skill のバージョンだけが上がることで確認する
- [x] 5.3 【人の作業】Console で Environment key を発行し、`.env` に `ANTHROPIC_ENVIRONMENT_ID` / `ANTHROPIC_ENVIRONMENT_KEY` を書いてもらう。その後、`scripts/worker_up.sh` でワーカーを起動し(API キーは渡さない)、`docker inspect` の環境変数に `ANTHROPIC_API_KEY` が無いことを確認する
- [x] 5.4 `src/verify/managed.py` に、セッションの作成、依頼の送信、idle までのイベント収集、終了を実装する。マーカーファイルを読む依頼で、応答にマーカー値が出ることを live テストで確認する
- [x] 5.5 `tests/test_managed_skills.py`(live)で、①パスを示さない自然な依頼と、②スキルのパスを示した依頼を実行し、`results/managed_*.json` に保存する。スクリプトの出力にコンテナのマーカーが含まれるか、応答が合言葉を述べているかを、文字列照合と Jev で判定する
- [x] 5.6 `docker exec` で `ls -laR /workspace/skills` と `which python3` を取り、`results/managed_layout.txt` に保存する(スキルの配置と、スクリプトの実行権限の確認)

## 6. まとめ

- [x] 6.1 `results/jev_summary.json` に、すべての Jev 判定、文字列照合の結果、食い違い、usage の合計を出力する
- [x] 6.2 `REPORT.md` を書く。結論の表(方式・条件ごとに、スキルのパス / 参照ファイルの読み取り / スクリプトの実行場所 / 応答の判定)、tool 呼び出しの抜粋、D4 のパス置き換えの注記、費用を含める
- [x] 6.3 `README.md` に、準備(Docker、`.env`、Environment key の発行)、実行コマンド、片付け手順を書く(Agent の archive は取り消せないので手動で行うと明記する)
- [x] 6.4 `grep` で、`results/`、`REPORT.md`、`README.md` に `.env` のトークンが含まれていないことを確認する。`uv run pytest -m "not live"` と `uv run pytest -m live` の結果を REPORT.md に記録する
