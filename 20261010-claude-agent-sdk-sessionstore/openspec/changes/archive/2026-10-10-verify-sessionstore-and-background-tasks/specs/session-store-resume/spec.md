# Spec Delta

## Purpose

Claude Agent SDK のセッション保存先を別実装の SessionStore に差し替えても、保存した会話を復元して継続できることを検証可能にする。

## ADDED Requirements

### Requirement: 自作 SessionStore がコントラクトを満たす
自作 SessionStore は、SDK 同梱の conformance テストをすべて通過しなければならない(SHALL)。

#### Scenario: conformance テストの通過
- **WHEN** 自作ストアのファクトリを conformance テストに渡して実行する
- **THEN** 必須メソッドに関するテストがすべて成功する

### Requirement: ストアから復元した続きの対話で tool 結果を参照できる
システムは、先行の対話で tool が返した結果が最終返答テキストに含まれていなくても、同じストアから `resume` した続きの対話でその結果を参照できなければならない(MUST)。

#### Scenario: 返答に出ない tool 結果の参照
- **WHEN** 最終返答に出さない指示つきで、固有の値(例: ランダムなトークン文字列)を返す tool を呼ばせ、`session_id` を記録する
- **AND** 新しいプロセス/ストア接続から同じストアと `resume=session_id` で「先ほどの tool の結果の値を答えて」と尋ねる
- **THEN** 応答に固有の値が含まれる

#### Scenario: ローカル transcript に依存しない
- **WHEN** 先行セッションのローカル transcript を削除(または別の `CLAUDE_CONFIG_DIR` を使用)してから resume する
- **THEN** ストアの内容のみで会話が復元され、同じ値を参照できる

### Requirement: 保存内容の検証
システムは、ストアに保存された entry に tool 結果が含まれることを直接確認できなければならない(SHALL)。

#### Scenario: ストア内容の確認
- **WHEN** 先行の対話後にストアの `load` を直接呼ぶ
- **THEN** 返された entry の中に tool 結果の固有値が含まれる

### Requirement: サブエージェントの transcript を保持する
システムは、サブエージェントの transcript を主 transcript とは別の key でストアに保存し、復元できなければならない(MUST)。

#### Scenario: サブエージェント経由の tool 結果
- **WHEN** サブエージェントに tool を呼ばせ、新しいストアインスタンスと別の config dir から resume する
- **THEN** サブエージェントの transcript がストアに保存されており、続きの対話でその値を参照できる

### Requirement: コンパクションの扱いを記録する
システムは、コンパクション後にストアへ追記される内容と、コンパクション後の復元で参照できる情報の範囲を記録しなければならない(MUST)。

#### Scenario: /compact 後のストア内容
- **WHEN** `/compact` を実行した後にストアを読む
- **THEN** 圧縮前の entry は残り、境界と要約の entry が追記されている
- **AND** 要約に tool 結果が含まれるかを観測結果として記録する

### Requirement: 検証結果の記録
システムは、標準ストアと自作ストアそれぞれの成否と、差異・制約を報告書に記録しなければならない(MUST)。

#### Scenario: 報告書の作成
- **WHEN** 全テストを実行し終える
- **THEN** `REPORT.md` に各シナリオの成否と所見が記載される
