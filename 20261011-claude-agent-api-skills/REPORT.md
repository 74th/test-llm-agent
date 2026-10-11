# 検証レポート: サンドボックス内でのスキルの扱い

Claude Agent SDK と Claude Managed Agents(self-hosted environment)について、スキル(`SKILL.md`、参照ファイル、Python スクリプト)がどこに置かれ、どこから読まれ、どこで実行されるかを、ローカルの Docker で確かめた。モデルは両方 `claude-haiku-5-5`。GKE Agent Sandbox は使っていない(sandboxd を Docker で動かした)。

- 検証用スキル: `skills/sandbox-probe/`(`SKILL.md`、`reference.md` に合言葉 `KUMQUAT-7412`、`scripts/probe.py` が `PROBE_MARKER` などを出力)
- sandboxd: kubernetes-sigs/agent-sandbox `v1.0.6`。コンテナには `/etc/sandbox-marker`(`SANDBOXD-LOCAL-a91f`)がある。ホストには無い
- ワーカー: `/etc/sandbox-marker` は `CMA-WORKER-LOCAL-5c2e`
- 生データ: `results/sdk_{A,B,C}.json`、`results/managed_*.json`、`results/managed_layout.txt`、`results/jev_summary.json`

## 結論

1. **Agent SDK では、スキルの `SKILL.md` はホスト側から読まれる。それ以外のスキルのファイルは、自分でサンドボックスに置かなければならない。**
   - Skill tool はスキルの本文に `Base directory for this skill: <ホストのパス>` を付けて返す。モデルは、このホストのパスをそのままサンドボックス用の tool に渡す。
   - サンドボックスにスキルのファイルが無ければ、参照ファイルの読み取りもスクリプトの実行も失敗する(条件 A)。
   - 同じパスにファイルをコピーしておけば成功する(条件 B)。スクリプトはサンドボックスで実行され、マーカーがサンドボックスの値になった。
2. **スクリプトの実行場所は、使う tool で決まる。** スキルの機能がスクリプトを実行するわけではない。ホストの Read で参照ファイルを読めても、スクリプトはサンドボックスで実行され、ホストのパスを持たないので動かない(条件 C)。
3. **Managed Agents では、スキルはワーカーコンテナの `/workspace/skills/<name>/` に、セッションごとにダウンロードされる。** 参照ファイルも Python スクリプトも同じ場所に置かれ、スクリプトはコンテナの中で `python3` により実行された。コピーの仕組みを自分で作る必要はない。
   - セッションが終わると `/workspace/skills` は空になる。
   - スクリプトの実行権限は付かない(`probe.py` は `0644`)。`python3 scripts/probe.py` なら動く。直接実行する形式のスクリプトは動かない。
   - Skill tool は無く、モデルは `read` / `glob` / `bash` で自分でファイルを探して読む。今回の依頼ではパスを教えなくても、自分で `glob` と `bash` で `/workspace/skills/sandbox-probe` を見つけて成功した。

## 結果の表

| 方式・条件 | スキルのパス | 参照ファイルの読み取り | スクリプトの実行場所 | 応答の判定(文字列 / Jev) |
|---|---|---|---|---|
| SDK A: コピーなし | ホストのパス `<tmp>/project/.claude/skills/sandbox-probe`。サンドボックスには存在しない | 失敗(`sandbox_read_file` が NOT_FOUND) | 失敗(exit 2。ファイルが無い) | 合言葉・マーカーとも なし / なし。「失敗した」と述べている(Jev 0.98) |
| SDK B: コピーあり | 同上。`/workspace/.claude/skills/sandbox-probe` に置き換えて読まれた | 成功(`sandbox_read_file`) | サンドボックス(`PROBE_MARKER: SANDBOXD-LOCAL-a91f`、`PROBE_SCRIPT: /workspace/.claude/skills/...`) | 合言葉・マーカーとも あり / あり(Jev 0.87 / 0.97)。「失敗した」は 0.03 |
| SDK C: ホストの Read あり | ホストのパス。サンドボックスには存在しない | 成功(ホストの `Read`) | 失敗(サンドボックスにファイルが無く exit 2) | 合言葉 あり(Jev 0.98)、マーカー なし(Jev 0.01)。「失敗した」と述べている(Jev 0.90) |
| Managed: 自然な依頼 | `/workspace/skills/sandbox-probe/`(モデルが `glob` で発見) | 成功(`bash cat`) | コンテナ(`PROBE_MARKER: CMA-WORKER-LOCAL-5c2e`、`PROBE_SCRIPT: /workspace/skills/sandbox-probe/scripts/probe.py`) | あり / あり(Jev 0.98 / 0.98)。「失敗した」は 0.02 |
| Managed: パスを示した依頼 | 同上(プロンプトで指定) | 成功(`read`) | コンテナ(同上) | あり / あり(Jev 0.98 / 0.98)。「失敗した」は 0.02 |

文字列照合と Jev の判定の食い違いは、すべての応答で 0 件(`results/jev_summary.json` の `string_vs_jev_mismatches`)。

## tool 呼び出しの抜粋

### SDK A(コピーなし)
```
Skill                          {"skill":"sandbox-probe"}
sandbox_read_file  raw: <tmp>/project/.claude/skills/sandbox-probe/reference.md
                   mapped: /workspace/.claude/skills/sandbox-probe/reference.md   → NOT_FOUND
sandbox_exec       python3 <tmp>/project/.claude/skills/sandbox-probe/scripts/probe.py
                   → exit 2: can't open file '/workspace/.claude/skills/sandbox-probe/scripts/probe.py'
```

### SDK B(コピーあり)
```
Skill                          {"skill":"sandbox-probe"}   → 本文に "Base directory for this skill: <tmp>/project/.claude/skills/sandbox-probe"
sandbox_read_file  <tmp>/project/.claude/skills/sandbox-probe/reference.md      → 合言葉 KUMQUAT-7412
sandbox_exec       python3 -I <tmp>/project/.claude/skills/sandbox-probe/scripts/probe.py
  → PROBE_HOST: <コンテナ ID>
    PROBE_MARKER: SANDBOXD-LOCAL-a91f
    PROBE_CWD: /workspace
    PROBE_SCRIPT: /workspace/.claude/skills/sandbox-probe/scripts/probe.py
    PROBE_PYTHON: /usr/local/bin/python3
```
どの条件でも、呼ばれた tool は `Skill`、`mcp__sandbox__*`、(条件 C だけ)`Read` のみ。Bash / Write / Edit / Glob / Grep は一度も呼ばれていない。

### Managed: コンテナ内の配置(`results/managed_layout.txt`、セッション実行中に `docker exec` で取得)
```
/workspace/skills                        drwx------
/workspace/skills/sandbox-probe          drwx------
  SKILL.md        -rw-r--r--   827
  reference.md    -rw-r--r--    54
  scripts/probe.py -rw-r--r--  606      ← 実行ビットなし
which python3 → /usr/local/bin/python3
```

## D4: パスの置き換えについての注記

サンドボックス用の tool は、引数に含まれるホストのプロジェクトのパス(`<tmp>/project`)を `/workspace` に置き換えてから sandboxd に渡している(設計 D4)。モデルはホストのパスのまま呼んでおり、**条件 A・B・C の結果は置き換えありのもの**である。置き換え前後の値は `results/sdk_*.json` の `sandbox_calls[].raw` / `mapped` に記録している。

置き換えが無ければ、B でもホストのパスはサンドボックスに存在しないので、成功しない。実運用では、次のどれかが必要になる。
- スキルをサンドボックス内の、ホストと同じ絶対パスに置く(今回は採用していない)
- tool 側でパスを置き換える(今回の構成)
- スキル側のパスを、スキルのディレクトリからの相対パスだけにして、cwd をスキルのディレクトリにする

## 設計との違い・実装で分かったこと

- design D3 の `tools=[]` だと Skill tool も外れ、スキルを呼べない。`tools=["Skill"]`(条件 C は `["Skill", "Read"]`)にした。
- sandboxd の `Execute` は argv で受け取るため、クライアントが `["/bin/sh", "-c", command]` に包んでいる。呼び出しの間で状態(`cd` など)は持ち越されない。
- sandboxd のファイル API のパスは `/workspace` からの相対として解釈される。`/etc/x` のような root の外の絶対パスは `/workspace/etc/x` になり、サンドボックス内のファイルを `cat /etc/x` と同じには読めない。
- Managed Agents のモデルは、一度「`/etc/sandbox-marker` は作業ディレクトリの外なので `read` できない」と答えて、`bash` に切り替えなかった(`bash` で読むよう指示すれば取得できる)。
- 結果はモデルの動きで揺れる(例: SDK A で `find /` を試す、C で `cat /etc/sandbox-marker` を試す)。表の値は最終実行のもの。結論に影響する差ではなかった。

## 費用とテストの結果

- Agent SDK(haiku 5.5、最終実行): A 約 $0.0013、B 約 $0.0009、C 約 $0.0014
- Managed Agents: 1 セッション当たりの出力は 100〜1,100 トークン程度(`results/managed_*.json` の `usage`)
- Jev: 5 応答 × 3 問 = 15 回(`results/jev_summary.json`)
- `uv run pytest -m "not live"`: **24 passed**(sandboxd を起動した状態)
- `uv run pytest -m live`: **10 passed**(Jev、SDK のスモークと条件 A/B/C、Managed のマーカー・自然な依頼・パス指定・配置の確認)
- 認証情報の確認: `.env` の `CLAUDE_API_KEY` / `JEV_API_TOKEN` / `ANTHROPIC_ENVIRONMENT_KEY` の値が `results/`、`REPORT.md`、`README.md` に含まれないことを `grep -F` で確認した
