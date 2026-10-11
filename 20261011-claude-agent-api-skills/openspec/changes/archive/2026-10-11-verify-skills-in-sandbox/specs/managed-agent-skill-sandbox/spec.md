# Spec Delta

## Purpose

Claude Managed Agents で、Skills API に事前登録したスキルが、self-hosted environment のワーカーコンテナにどう配置され、スキル内の参照ファイルと Python スクリプトがコンテナ内でどう使われるかを観測して記録する。

## ADDED Requirements

### Requirement: スキルの事前登録とエージェントへの添付
システムは、検証用スキル `sandbox-probe`(Agent SDK の検証と同じ内容)を Skills API に登録し、Agent に添付できなければならない(SHALL)。何度実行しても重複して作らない(MUST)。作成したリソースの ID はローカルのファイルに保存し、秘密の値は保存しない。

#### Scenario: 再実行
- **WHEN** 登録処理を 2 回実行する
- **THEN** Environment・Skill・Agent はそれぞれ 1 つのまま。スキルは新しいバージョンになり、Agent はそれを参照する

### Requirement: self-hosted ワーカーコンテナ
システムは、self-hosted environment のワーカーを Docker コンテナで起動できなければならない(SHALL)。コンテナには Python 3 とマーカーファイルを含める。Anthropic の API キーはコンテナに渡してはならない(MUST)。渡すのは Environment ID と Environment key だけである。

#### Scenario: コンテナでの tool 実行
- **WHEN** ワーカーを起動してセッションを作り、マーカーファイルを読むよう依頼する
- **THEN** 応答または tool 結果に、ビルド時に決めたマーカー値が含まれる

### Requirement: スキルの配置と実行の観測
システムは、スキルを使う依頼をセッションに送り、次の内容を記録しなければならない(SHALL)。
- コンテナ内でスキルのファイルが置かれたパス、ファイル一覧、ファイルの権限
- 参照ファイルをどのパスで読んだか、その結果
- Python スクリプトをどのコマンドで実行したか、その結果(マーカー、ホスト名、スクリプトの絶対パス)
- セッションのイベント列(tool 呼び出しと結果)とエージェントの最終応答

#### Scenario: 自然な依頼
- **WHEN** パスを指定せずに「sandbox-probe スキルを使って」と依頼する
- **THEN** モデルが自分でスキルを見つけて使えたかどうかが記録される

#### Scenario: パスを示した依頼
- **WHEN** 自然な依頼でスキルが使われなかった場合に、スキルの置き場所をプロンプトで示して依頼する
- **THEN** スクリプトがコンテナ内で実行され、出力にコンテナのマーカーが含まれることが確認される。成功しない場合は、その理由が記録される

### Requirement: リソースの片付け手順
システムは、作成した Anthropic 側のリソース(Agent、Environment、Skill)とローカルの Docker リソースの片付け手順を文書にしなければならない(MUST)。取り消せない操作(Agent の archive など)は自動で実行してはならない(MUST)。

#### Scenario: 片付け手順の確認
- **WHEN** README を読む
- **THEN** リソースごとの片付けコマンドと、取り消せない操作についての注意が書かれている
