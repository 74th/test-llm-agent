# Hermes Agent + ローカル Ollama

ホストで動作している Ollama の OpenAI 互換 API (`127.0.0.1:11434`) を利用して、Hermes Agent を Docker Compose で動かす構成です。使用モデルは `gemma4:26b-a4b-it-qat` です。

## 初回セットアップ

1. Hermes Agent の公式ソースを取得します。

   ```bash
   git clone --depth 1 https://github.com/NousResearch/hermes-agent.git hermes-agent-src
   ```

   次に、雛形からローカル設定ファイルを作成します。

   ```bash
   cp hermes-data/config.example.yaml hermes-data/config.yaml
   ```

2. Ollama を 64K 以上のコンテキスト長で起動します。Hermes Agent は 64K 未満のコンテキストでは利用できません。

   ```bash
   OLLAMA_CONTEXT_LENGTH=64000 ollama serve
   ollama ps
   ```

   `ollama ps` の `CONTEXT` 列が `65536` 以上であることを確認します。

3. コンテナをビルドして起動します。

   ```bash
   docker compose up -d --build
   ```

`network_mode: host` を使っているため、コンテナ内の `127.0.0.1:11434` はホストの Ollama を指します。

## Dashboard

Dashboard は `0.0.0.0:9119` で待ち受けます。自宅 LAN 内の別 PC からは、次の URL を開きます。

```text
http://<このサーバーのLAN IP>:9119
```

Basic 認証は Git 管理しない `hermes-data/config.yaml` の `dashboard.basic_auth` で設定します。`password_hash` は Hermes 形式の `scrypt$...` を使います。Apache `.htpasswd` の bcrypt (`$2y$...`) は利用できません。

パスワードハッシュを作るには、起動済みのコンテナで次を実行します。

```bash
docker compose exec dashboard python -c \
  "from plugins.dashboard_auth.basic import hash_password; print(hash_password(\"パスワード\"))"
```

生成結果を設定します。`secret` は 32 バイト以上のランダム値にしてください。

```yaml
dashboard:
  basic_auth:
    username: admin
    password_hash: "scrypt$..."
    secret: "ランダムな署名鍵"
```

設定を変更したら dashboard を再作成します。

```bash
docker compose up -d --force-recreate dashboard
```

## 自作スキル

Hermes の自作スキルは `hermes-data/skills/<スキル名>/SKILL.md` に置きます。このリポジトリでは、バス時刻表スキルを次の場所に保存しています。

```text
hermes-data/skills/bus-timetable/SKILL.md
```

起動済みコンテナから検出状況を確認できます。

```bash
docker compose exec gateway hermes skills list
```

`hermes-data` にはセッション、認証情報、組み込みスキルなどの実行時データが保存されます。これらをコミットしないよう `.gitignore` で無視しています。設定の雛形 `hermes-data/config.example.yaml` はコミット対象です。一方で、上記の `bus-timetable/SKILL.md` だけは例外として Git 管理します。新しい自作スキルもコミットしたい場合は、`.gitignore` に同様の例外を追加してください。

## よく使うコマンド

```bash
# 起動状態の確認
docker compose ps

# ログの表示
docker compose logs -f gateway
docker compose logs -f dashboard

# 停止（永続データは残る）
docker compose down
```
