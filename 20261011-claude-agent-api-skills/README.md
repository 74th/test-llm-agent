# verify-skills-in-sandbox

Claude Agent SDK と Claude Managed Agents(self-hosted environment)で、スキルのファイルがサンドボックスのどこで読まれ・実行されるかを、ローカルの Docker で確かめる。結果は [REPORT.md](REPORT.md)。

## まとめ

モデルは両方 `claude-haiku-5-5`。GKE は使わず、sandboxd をローカルの Docker で動かして確認した。

### Claude Agent SDK(コマンド実行・ファイル操作を sandboxd 経由の tool に置き換えた場合)

- `SKILL.md` は Skill tool がホスト側から読む。本文には `Base directory for this skill: <ホストのパス>` が付いて返り、モデルはそのパスのままサンドボックス用の tool に渡す。
- 参照ファイルと Python スクリプトは、**自分でサンドボックスにコピーしない限りサンドボックスには存在しない**。
- スクリプトの実行場所は、使う tool で決まる(スキルの機能が実行するわけではない)。

| 条件 | 参照ファイル | スクリプト |
|---|---|---|
| A: コピーなし | 失敗 | 失敗(ファイルが無い) |
| B: 同じパスにコピー | 成功 | **サンドボックスで実行**(`PROBE_MARKER` がサンドボックスの値) |
| C: ホストの Read を許可 | ホストから読めた | 失敗(サンドボックスにファイルが無い) |

注意: 結果は、ホストのプロジェクトのパスを `/workspace` に置き換えた場合のもの。置き換えが無いと B でも失敗する。実運用では、同じ絶対パスに置く、tool で置き換える、スキルを相対パスで書いて cwd をスキルのディレクトリにする、のどれかが要る。

### Claude Managed Agents(self-hosted environment、ワーカーは Docker)

- スキルは Skills API に事前登録し、ワーカーが**セッションごとに `/workspace/skills/<name>/` へダウンロード**する。SKILL.md・参照ファイル・スクリプトが同じ場所に揃うので、コピーの仕組みは要らない。セッションが終わると消える。
- スクリプトは**コンテナ内で実行**された(`PROBE_MARKER` がコンテナの値)。
- 実行権限は付かない(`probe.py` は `0644`)。`python3 scripts/xxx.py` の形なら動くが、直接実行する形式は動かない。
- Skill tool は無く、モデルが `read` / `glob` / `bash` で探す。パスを教えない自然な依頼でも、`glob` で見つけて成功した。

### 設計との違い・実装で分かったこと

- `tools=[]` だと Skill tool も外れるため、`tools=["Skill"]` にした。
- sandboxd のコマンドは argv で渡され(呼び出しの間で `cd` などの状態は持ち越されない)、ファイル API のパスは `/workspace` からの相対として解釈される。

詳しい表、tool 呼び出しの抜粋、費用は [REPORT.md](REPORT.md)。

## 準備

1. Docker と uv(Python 3.13)を用意する。
2. `.env` に次を書く(`.env` は git に入れない)。
   ```
   CLAUDE_API_KEY=...
   JEV_API_TOKEN=...
   ```
3. `uv sync`
4. Agent SDK の検証用に sandboxd を起動する(`127.0.0.1` だけに公開)。
   ```
   scripts/sandboxd_up.sh
   ```
   gRPC のスタブは `src/verify/sandboxd_pb/` に生成済み。作り直すときは `scripts/gen_sandboxd_pb.sh`。
5. Managed Agents の検証用に、Anthropic 側のリソースを作る(2 回実行しても増えない。Skill は毎回新しいバージョンになる)。
   ```
   uv run python scripts/provision.py     # .provisioned.json に ID だけを保存
   ```
6. **人の作業**: Console で、作成した Environment(`verify-skills-in-sandbox`)の Environment key を発行し、`.env` に追記する。
   ```
   ANTHROPIC_ENVIRONMENT_ID=env_...
   ANTHROPIC_ENVIRONMENT_KEY=...
   ```
7. ワーカーを起動する(コンテナに渡すのは Environment の ID と key だけ。API キーは渡さない)。
   ```
   scripts/worker_up.sh
   ```

## 実行

```
uv run pytest -m "not live"       # API を使わないテスト(sandboxd の起動が必要なものがある)
uv run pytest -m live             # Anthropic API / Jev を使うテスト
uv run python scripts/jev_summary.py   # results/jev_summary.json を作る
```

Environment key が `.env` に無いか、ワーカーが起動していない場合、Managed Agents のテストは skip される。結果は `results/` に出る(git に入れない)。

## 片付け

- ローカルの Docker
  ```
  scripts/sandboxd_down.sh
  scripts/worker_down.sh
  docker rmi verify-sandboxd:dev verify-cma-worker:dev
  ```
- Anthropic 側(`.provisioned.json` の ID を使う)。**Agent の archive は取り消せないので、自動では実行しない。不要になったことを確かめてから手動で行う。**
  ```
  # Agent: 取り消せない
  uv run python -c "import anthropic,json;from verify.config import anthropic_api_key as k;anthropic.Anthropic(api_key=k()).beta.agents.archive(agent_id=json.load(open('.provisioned.json'))['agent_id'])"
  ```
  Skill と Environment は、先に Agent を archive してから消す(Agent が参照している間は消せない場合がある)。
  ```
  # Skill(バージョンがある場合は先に skills.versions.delete でバージョンを消す)
  uv run python -c "import anthropic,json;from verify.config import anthropic_api_key as k;anthropic.Anthropic(api_key=k()).skills.delete(skill_id=json.load(open('.provisioned.json'))['skill_id'])"
  # Environment
  uv run python -c "import anthropic,json;from verify.config import anthropic_api_key as k;anthropic.Anthropic(api_key=k()).beta.environments.archive(environment_id=json.load(open('.provisioned.json'))['environment_id'])"
  ```
  Environment key は Console で失効させる。
  各セッションは、テストが終わるときに archive している。
- ローカルのファイル: `.provisioned.json`、`results/`、`.env` の `ANTHROPIC_ENVIRONMENT_*`
