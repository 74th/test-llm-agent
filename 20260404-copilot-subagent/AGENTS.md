シンプルなタスク管理システムのWebAPI

- server/api.py: REST API定義
- memdb: シンプルなインメモリDB
- domain: ドメインレイヤ
  - entity: エンティティ定義
  - usecase: ユースケース定義

ユニットテストは以下で実行する

```
uv run python -m unittest discover -p '*_test.py'
```
