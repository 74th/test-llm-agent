---
name: sandbox-probe
description: 実行環境(サンドボックス)の調査を行うスキル。「sandbox-probe」「実行環境を調べて」「サンドボックスの確認」と頼まれたときに使う。
---

# sandbox-probe

実行環境を調べて、決まった形式で報告する。

## 手順

1. このスキルのディレクトリにある `reference.md` を読み、そこに書かれている合言葉を得る。
2. このスキルのディレクトリにある `scripts/probe.py` を Python 3 で実行する。
3. 次の形式で報告する。読めなかった・実行できなかった場合は、その旨と、使ったパスやコマンド、エラーの内容を書く。

```
PASSPHRASE: <reference.md の合言葉>
SCRIPT_OUTPUT:
<scripts/probe.py の標準出力をそのまま>
```
