---
name: container-toolchain
description: このコンテナで使えるCLIツール(bq/gcloud/uv)
---

このセッションが動いているコンテナには、Python本体は入っていませんが以下が使えます。

- `bq` / `gcloud`（google-cloud-sdk）: BigQueryへのアクセスなどはこれで直接実行できます。
- `uv`: Pythonスクリプトをその場で実行できます。ライブラリが必要な場合は `uv run --with google-cloud-bigquery script.py` のように `--with` で指定すれば、仮想環境の準備なしにそのまま動きます。

BigQueryにアクセスする場合、`bq` コマンドと `uv run --with google-cloud-bigquery` のどちらでも到達できます。認証情報（`GOOGLE_APPLICATION_CREDENTIALS`）はコンテナに用意済みです。
