# self-hosted-runner-container Specification

## Purpose

独自にビルドしたコンテナイメージで Claude Code の self-hosted runner を動かすための、イメージの中身と 2 つの実行モード（常駐 runner / セッション毎コンテナ）の振る舞いを定める。

## Requirements

### Requirement: Runner イメージが self-hosted runner を実行できる

コンテナイメージは、`claude self-hosted-runner` サブコマンドを認識するバージョン（v2.1.224 以降）の Claude Code バイナリと、git 2.34 以降を含んでいなければならない（SHALL）。Claude Code のバージョンはビルド引数で固定され、イメージ内で auto-update されてはならない（MUST NOT）。

#### Scenario: バイナリが runner サブコマンドを持つ

- **WHEN** ビルドしたイメージで `claude self-hosted-runner --help` を実行する
- **THEN** `--environment-secret-file` を含む runner の usage が出力される

#### Scenario: バージョンが固定されている

- **WHEN** ビルド引数で指定したバージョンとイメージ内の `claude --version` を比較する
- **THEN** 両者が一致する

### Requirement: git のコミット identity がイメージに設定されている

セッションがコミットできるよう、イメージは system スコープの git identity と `safe.directory` を設定していなければならない（SHALL）。

#### Scenario: identity が設定済み

- **WHEN** コンテナ内で `git config --system --get user.email` を実行する
- **THEN** 空でない値が返る

### Requirement: シークレットがイメージに焼き込まれない

environment secret、GitHub PAT、その他の資格情報はイメージレイヤに含まれてはならない（MUST NOT）。これらは実行時にファイルまたは環境変数として供給される（SHALL）。

#### Scenario: イメージ内にトークンがない

- **WHEN** ビルド済みイメージのファイルシステムと build history を走査する
- **THEN** environment secret および GitHub PAT の値が見つからない

### Requirement: 常駐モードで runner がセッションを連続処理する

常駐モードでは、runner コンテナは environment secret を使って environment に登録し、セッション終了後も同一コンテナのまま次のセッションをポーリングしなければならない（SHALL）。コンテナが終了した場合は自動的に再起動される（SHALL）。

#### Scenario: runner が environment に登録される

- **WHEN** 常駐モードでコンテナを起動する
- **THEN** runner のログに登録成功が出力され、claude.ai の Cloud environments 画面で当該 environment が Healthy になる

#### Scenario: 2 回目のセッションを同じコンテナが拾う

- **WHEN** 1 回目のセッションが完了したのち、同じ environment へ 2 回目のセッションを投げる
- **THEN** 同一のコンテナのログに 2 回目の `Picked up session` が出力される

### Requirement: セッション毎モードでセッション専用のワークロードが起動する

セッション毎モードでは、orchestrator プロセスが spawn 要求をポーリングし、要求ごとに新しいワークロードを 1 つ起動しなければならない（SHALL）。起動されたワークロードは work-order JWT で environment に登録し、`--capacity 1` で動作し、セッション終了とともに破棄される（SHALL）。environment secret は orchestrator 側にのみ存在し、セッションを実行するワークロードに渡されてはならない（MUST NOT）。

検証では Docker コンテナをワークロードとして用いる。要件はワークロードの実体（コンテナ / Pod / VM）を規定しない。

#### Scenario: セッションごとに新しいワークロードが作られる

- **WHEN** 同じ environment へ連続して 2 つのセッションを投げる
- **THEN** それぞれ別のワークロードが起動し、セッション終了後に自動的に破棄される

#### Scenario: spawn 要求が冪等に扱われる

- **WHEN** 同一の spawn 要求が再配信される
- **THEN** 起動されるワークロードは高々 1 つである

#### Scenario: セッションのワークロードが environment secret を持たない

- **WHEN** 起動されたワークロードの環境と設定を確認する
- **THEN** environment secret は存在せず、work-order JWT のみが渡されている

### Requirement: spawn の実装がプロビジョナから分離されている

orchestrator が呼ぶフックは、Anthropic 側の契約（work-order の受け取り、冪等性、終了コード）を引き受ける層と、実際にワークロードを起動するプロビジョナ層に分離されていなければならない（SHALL）。プロビジョナ層は文書化された内部契約のみを入力とし、Anthropic のフック仕様に直接依存してはならない（MUST NOT）。プロビジョナは設定によって差し替え可能でなければならない（SHALL）。

#### Scenario: プロビジョナを差し替えられる

- **WHEN** 別のプロビジョナを指す設定でorchestrator を起動する
- **THEN** 契約を引き受ける層に変更を加えることなく、そのプロビジョナが呼び出される

#### Scenario: プロビジョナがフック仕様に依存しない

- **WHEN** プロビジョナのスクリプトを読む
- **THEN** `CLAUDE_RUNNER_` で始まる変数を直接参照していない

#### Scenario: work-order JWT が引数にも環境変数にも現れない

- **WHEN** プロビジョナが呼び出される
- **THEN** work-order JWT は標準入力から渡され、コマンドライン引数や呼び出し側の環境変数には現れない

### Requirement: プロビジョナが終了コードの契約を守る

プロビジョナは、投入成功を 0、リトライ可能な失敗を 1、リトライ不可能な失敗を 2 以上で表さなければならない（SHALL）。契約を引き受ける層はこの終了コードを変換せずに orchestrator へ返さなければならない（SHALL）。失敗時、原因は stderr に書かれ、秘密情報を含んではならない（MUST NOT）。

#### Scenario: 終了コードがそのまま伝わる

- **WHEN** プロビジョナが 2 で終了する
- **THEN** フック全体も 2 で終了する

#### Scenario: 失敗理由に秘密情報が出ない

- **WHEN** プロビジョナが失敗して stderr に出力する
- **THEN** work-order JWT および GitHub トークンの値が含まれない

### Requirement: 実運用プロビジョナへの移行経路が文書化されている

内部契約と、検証用プロビジョナ以外の実装が満たすべき規約（冪等キーの使い方、リトライしないこと、終了コード、JWT の渡し方）が文書化されていなければならない（SHALL）。

#### Scenario: 別プロビジョナを書き起こせる

- **WHEN** GKE Pod で起動したい実装者が文書を読む
- **THEN** 受け取る入力と守るべき規約が分かり、検証用プロビジョナを読まずに新しい実装を書き始められる
