# Design

## Context

動機は proposal.md を参照。リポジトリは空(`openspec/` と `.env`、`xprivate/` のみ)で、同系統の過去検証(`20260221-claude-agent-sdk`)は Python 3.13 + uv + `claude-agent-sdk` を使っている。これに合わせる。

調査済みの事実(公式ドキュメント):
- Python では `ClaudeAgentOptions(session_store=..., resume=session_id)` でストアから復元できる。ストアは `append(key, entries)` と `load(key)` が必須で、`list_sessions` / `list_session_summaries` / `delete` / `list_subkeys` は任意。
- subprocess は常にローカルへ先に書き、SDK がそれをストアへミラーする(best-effort、失敗時は `mirror_error`)。store 経由の resume ではローカルのコピーは実行終了時に削除される。再配信に備え `entry.uuid` で重複排除が必要。
- Python は resume 時に認証情報と `.claude.json` のみ一時 config dir へコピーする。API キーは環境変数 `ANTHROPIC_API_KEY` で渡すのが安全。
- `claude_agent_sdk.testing.run_session_store_conformance` が conformance テストを提供する。
- Jev は TypeSafe の System One モデル。公式 API は `POST https://api.typesafe.ai/v1/systemone`(`Authorization: Bearer <key>`)で、`{state, model, questions}` を送ると `answers`(noul は 0〜1 の値、choice/score は確率と confidence)と `usage` が返る。モデルは `jev-latest`。Python SDK は `typesafe-sdk`(`TypeSafeClient`、`TYPESAFE_API_KEY` を読む)。文章は生成しない。

未確認(実装時に実測で確定する):
- バックグラウンド tool(Bash の `run_in_background` 等)の完了が、SDK の `query()` / `ClaudeSDKClient` で追加のアシスタント応答を引き起こすか。

## Goals / Non-Goals

**Goals:**
- 3つの capability の各シナリオを、再実行可能な pytest として表現する。
- 結果(成否、制約、コスト)を `REPORT.md` にまとめる。

**Non-Goals:**
- 本番品質のストア実装(Redis/Postgres 等)。検証用の最小実装にとどめる。
- Jev の一般的な性能評価。ここでは判定器として成立するかの確認のみ。
- TypeScript SDK の検証。

## Decisions

1. **言語/構成**: Python 3.13、uv、pytest + anyio。src に検証コード、tests にテスト。理由は過去検証との一貫性と、conformance スイートが Python に同梱されていること。
2. **自作ストア**: ファイル(JSONL、session key ごとに1ファイル)の `FileSessionStore` を作る。`append` は `uuid` で重複排除する。ストアを差し替えられること自体の確認が目的なので、`InMemorySessionStore` との差は持ち込まない。代替案の SQLite は列設計が増えるため見送り、必要なら後続で追加する。
3. **tool 結果が返答に出ない状況の作り方**: SDK の in-process MCP tool(`@tool`)でランダム値を返す `issue_token` を用意し、システムプロンプトと指示で「値は返答に書かない」と指定する。結果が返答テキストに出ていないことを先に assert し、出てしまった場合は前提不成立としてテストを失敗でなく skip/リトライ扱いにする。
4. **復元の独立性**: resume は別の `CLAUDE_CONFIG_DIR` と新しいストアインスタンスで行い、ローカル transcript に頼っていないことを担保する。
5. **バックグラウンド検証は段階的に**: (a) `sleep` + 出力のコマンドを Bash の background 実行で起動、(b) 先行返答の ResultMessage を確認、(c) 待機中に別プロンプトを送る、(d) 完了後にメッセージが来るか観測する。標準機能で完了契機の応答が来なければ「非対応」と記録し、代替としてアプリ側で完了を検知し、完了通知を新しいプロンプトとして同一セッションへ resume 注入する方式を試す。待ち時間は実時間の制約から、まず30〜60秒で確認し、5分は最後に1回だけ手動マーク付きテストで確認する。
6. **Jev 判定ヘルパー**: 公式 `typesafe-sdk`(`TypeSafeClient.system_one`)を使う薄いヘルパー。state に応答テキスト、質問に「期待値に言及しているか(noul)」を入れ、noul が閾値(0.3 より大きければ合格。ユーザ指定)を超えれば合格。キーは Jev 公式(TypeSafe)のキーとして `JEV_API_TOKEN` を `TYPESAFE_API_KEY` へ渡す。OpenRouter は使わない。理由は、モデル出力の揺れを許容しつつ、固有値の存在のような決定的チェックは文字列一致も併用して比較できるため。
7. **モデル**: `claude-haiku-5-5` を `ClaudeAgentOptions(model=...)` で固定。`max_turns` と予算上限を設けてコストを抑える。
8. **秘密情報**: `.env` を `python-dotenv` で読み込み、`CLAUDE_API_KEY` を subprocess の `ANTHROPIC_API_KEY` として `options.env` に渡す。`.gitignore` に `.env` を追加し、ログにトークンを出さない。

## Risks / Trade-offs

- [LLM 出力の非決定性でテストが不安定] → 値は固有トークンで判定し、Jev は閾値判定。重要テストは複数回試行して成功率を報告書に書く。
- [Python SDK は apiKeyHelper を resume 時に引き継げない] → 環境変数でキーを渡す。
- [バックグラウンド完了契機の応答が SDK 標準では不可の可能性] → 非対応も有効な検証結果とし、代替方式の可否まで記録する。
- [Jev の API/SDK の仕様変更] → ヘルパーを1箇所に隔離する。
- [Jev は「LLM の応答を判定する」用途を想定した製品ではない可能性] → 判定器として精度が出なければその旨を結果として記録し、文字列一致を主、Jev を補助にする。
- [課金] → Haiku 固定、ターン数と文字数を抑制。Jev は従量課金。

## Open Questions

- Jev の `usage` にコストは含まれない(トークン数のみ)。コスト集計はトークン数で行う。
