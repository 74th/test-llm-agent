# ローカルLLMを試す

## なにか

LocalLLMマシンを使ったり、LocalLLMのデモをやったりして、学んだことの共有。

## 推論速度

Ryzen AI MAX +395の、メモリ96GBのマシンを購入した。
分かって購入したが、そこまで速くない。

Reditの投稿等で集めた数字

|                   | 搭載メモリ | TPOS(INT8) |
| ----------------- | ---------: | ---------: |
| DPG Spark         |       128G |       1000 |
| RTX 5090          |        32G |        838 |
| RTX 5070 Ti       |        16G |        351 |
| RTX 5070          |        12G |        246 |
| Ryzen AI MAX +395 |        96G |         76 |
| Apple M4          |        32G |         38 |
| Apple M4 Max      |       128G |         38 |

現状メモリの多いマシンであっても、GPUとは推論速度が桁が違う。

## ローカルLLM用モデル

### モデルの種類と見方

動かせるかどうかは Can I Run AI locally? というサイトが参考になる

https://www.canirun.ai/

GoogleがApacheライセンスでGemma 4を4月に発表した。

`Gemma 4 31B` の31Bはパラメータ数で、大きいほど、メモリも食うし、処理が重い。

`Gemma 4 E2B, E4B` は、Effective parameter 4B で、メモリは8B分使うが、計算量としては4Bですむ。エッジ向けモデル。

`Gemma 4 26B-A4B`は、MoE（Mixture-of-Experts）モデルで、26Bのパラメータがあるが、処理毎に利用するモデルを選択されて、実際の計算量はActive 4B ということ。メモリは食うが、計算は速い。

メモリがある程度あるが、能力を損なわせたくないならば、MoEモデルが有効そう。

### 量子化レベル

Gemma 4など元のモデルは16bit精度で学習されているが、それをさらに量子化して8、6、4bitにしても、そこまで推論能力が落ちないと言われている。

よって、ローカルLLMでは`Q4`と呼ばれる4bit量子化したモデルを使い、計算コストとメモリを抑えている。
16bit→4bitにしたら、メモリは1/4になる。
推論においてはInt8性能で見られるのもこのあたりのようである。

OllamaではQ4が使われるが、LM Studioでは選択できる。
同じ名前のモデルを使っていても、実は量子化モデルを使っていた、というのがあり得る。

## モデルとライブラリ

いくつかモデルファイルとライブラリがわかれている。

- llama.cpp
    - Ollama、LM Studioなどのバックエンドに使われる
    - GGUFというモデルフォーマットを使う
        - GGUFにはモデルの重み以外にも、モデルのフォーマットや、reasoningやtool call、visionの指示の仕方のテンプレートが含まれている
    - Gemma 4 MTP、QATに対応
- vLLM
    - Hugging Face形式のモデルを使う
    - config.jsonが別
    - Gemma 4 MTPに対応
- mlx-lm
    - Apple Silicon Mac向け
    - mlxモデルを使う
    - LM Studioのバックエンドとして使える

Macだとmlxが最適ではあるが、ライブラリによってはMTP等の機能が使えないなどがあり、モデルによって選ぶ必要がありそう。
また、環境 NVIDIA Cuda、AMD Vulcan、Apple Siliconなど対応がライブラリによって違う。

モデルファイルにはGGUFのように、重み以外にも実行に必要なパラメータや、テンプレートが含まれている。
テンプレートによって、モデル毎のtool callやreasoning、Visionの指定の仕方の違いを吸収してくれている。

> Gemma 4 26B-A4Bの例
>
> https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF/blob/main/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf

Gemma 4 MTPの対応は、vLLMが早く、3週間くらい遅れてllama.cppが対応した。
vLLM x Vulcan(AMD GPU) で試そうとしたが、動かなかった。

Ollama、LM Studioなど、llama.cppのラッパーして使いやすくしたものが広まっている。
しかし、llama.cppに指定できるパラメータに制限があったりして、llama.cppの全機能が使えるわけではない。

llama.cppには、サンプルコードとして、llama-severがありOpenAI互換APIとして使える。
Ollamaで使えない機能や、積極的に新しいモデルを使ってみたいならば、結局llama-serverを使うことになった。

## ローカルLLMの処理

1. トークン化: テキスト → トークンID列
2. 埋め込み: トークンID列 →　埋め込みベクトル
3. Transformer推論
4. デコード: トークンIDを選ぶ
5. デトークン化: トークンID列 → テキスト

### 対話の作り方

対話を作る場合、2回目以降は過去の履歴の続きから推論してくれると嬉しい。

llama.cppはKVキャッシュを持っており、過去の履歴のトークンを保持してくれる。

APIとしては、履歴のテキストを全部投げればよい。
トークンID列化した後に、KVキャッシュを引いて、続きから推論する形になる。

### Reasoningを積み込むかはテンプレート次第である

Reasoningを含む場合、以下の形になる

- 入力
  - システムプロンプト
  - ユーザプロンプト 1
- 出力
  - Reasoning 1
  - AIアウトプット 1

これで追加の対話を行う場合、以下の形になる

- 入力
  - システムプロンプト
  - ユーザプロンプト 1
  - AIアウトプット 1
  - ユーザプロンプト 2
- 出力
  - Reasoning 2
  - AIアウトプット 2

Reasoningは次のターンに持ち越さないのが普通らしい。
Gemma 4 GGUFのテンプレートでは「入力の最後にtool callの結果がある場合だけReasoningを追加する」となっていた。
テンプレートによって、このあたりを制御されているので、APIへのリクエストがそのまま適用されるとは思わない方がよさそう。

## MTP Drafters

Qwen 3.5、Gemma 4 は、MTP Draftersと呼ばれる機能がある。

1トークンずつ推論するのが基本だが、予測モデルを持っておき、それに合致すれば追加で1トークン予測モデルから取り出す。
予測と計算結果が合致すれば、予測通りとしてメモリ転送等のいくつかの処理をスキップできて、速くなるらしい。

https://note.com/npaka/n/n7e64b803037c

最大3倍速くなるらしい。

現状、llama.cppとvLLMが対応済み。
しかし、llama.cppをバックエンドに持つ、Ollama、LM StudioはGemma 4はまだ未対応。

## QAT

学習中に、4bit量子化をシミュレートしてモデル化して、量子化の損失を抑える技術らしい。
Gemma 4ではE2B、E4B、12B、26B-A4B、31Bが提供されている。

https://note.com/npaka/n/ndeef4df16dd2

## コンテキスト溢れは誰が責任を持つのか

OpenAI互換APIレベルでは、コンテキスト圧縮の機能はない。
コンテキストが溢れたらエラーが返る。

それらをラップするツールがコンテキスト溢れに対応して、コンテキスト圧縮のクエリを実行したりする。

LangChainのcreate_agentを使うと、複数の推論バックエンドでエージェントが作れるが、コンテキスト圧縮がミドルウェアとして提供されており、使うことができる。

## GitHub Copilotで使う

OpenAI互換API（llama.cppで使える）と、Ollamaに対応している。すぐ使える。

わりと、Gemma 4 26B-A4Bは実装ができる。

## ひとまずMacで使ってみたい

Ollamaが簡単。

```sh
#!/bin/bash

MODEL_NAME="gemma4:26b"
CONTEXT_SIZE=$((1024 * 128))

curl http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"$MODEL_NAME\",
    \"keep_alive\": -1,
    \"options\": {
      \"num_ctx\": $CONTEXT_SIZE
    }
  }'"
```

これで起動して、OpenAI互換APIとして使える。

## まだ実感してないこと

Gemma 4 は 128k コンテキストもある。
ローカルLLMはコンテキストが膨らんだときの考慮力が低いと言われているらしい。
まだ実感するほど試せてない。

## 発見だったことまとめ

- 大きいモデルを使うとメモリを食うが、計算量もかかり遅くなる。MoEモデルが効率的そう。
- モデルには量子化モデルが作られていて、小さくできるが、精度と相談である。
- モデルファイルは、対応ライブラリごとに異なっている。ライブラリごとに機能が異なっている。
- モデルファイルにはテンプレートがあり、モデル毎のReasoning、tool callの指定の仕方や、アウトプットを吸収している。
- テンプレートにより、載らない情報がある。Reasoningの内容は次のターンに持ち越されないことが多い。
- ライブラリにキャッシュ機構があり、履歴は全部投げても再計算されず、キャッシュが当たる。
- Gemma 4 MTP、QATが、llama.cpp最新版で使えてそこそこ早い。
