シンプルなタスク管理システムのWebAPI

- server/api.py: REST API定義
- memdb: シンプルなインメモリDB
- domain: ドメインレイヤ
  - entity: エンティティ定義
  - usecase: ユースケース定義

ユニットテストを実行する場合は、`.github/agents/python-unit-test-runner.agent.md` のカスタムエージェントを優先して使うこと。

ユニットテストは以下で実行する

```
uv run python -m unittest discover -p '*_test.py'
```
