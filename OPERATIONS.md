# Operations

## Service

- Unit: `karchitect.service`
- Working directory: `/home/kojima/work/karchitect`
- Bind: `0.0.0.0:18347`（内部トークン必須）
- Model: `gemma4:12b-it-qat`
- Ollama: `http://127.0.0.1:11434`

## Checks

```bash
systemctl --user status karchitect.service
set -a; . ./.env; set +a
curl -fsS \
  -H "X-KArchitect-Token: ${KARCHITECT_INTERNAL_TOKEN}" \
  -H "X-KArchitect-User: operations" \
  http://127.0.0.1:18347/health | jq .
journalctl --user -u karchitect.service -n 100 --no-pager
```

内部トークンを設定した環境では、`X-KArchitect-Token` と
`X-KArchitect-User` の両ヘッダーが必要です。一般利用者は
`https://kurage.exbridge.jp/karchitect.php` の共通X認証を経由します。

## Public deployment

```bash
./scripts/deploy.sh
```

公開PHPは許可したAPIルートだけを中継し、更新系リクエストにはCSRF検証を行います。
`public/karchitect_config.php` と `.env` のトークンを一致させ、どちらもGitへ追加しません。

## Data

- SQLite: `/home/kojima/work/karchitect/data/karchitect.db`
- PDF exports: `/home/kojima/work/karchitect/data/exports/`

`data/`はGit管理しません。バックアップ時はサービスを停止するかSQLite backup APIを使用します。

## Update

```bash
git status --short --branch
git pull --rebase origin main
git submodule update --init --recursive
.venv/bin/pip install -r requirements.txt
systemctl --user restart karchitect.service
set -a; . ./.env; set +a
curl -fsS \
  -H "X-KArchitect-Token: ${KARCHITECT_INTERNAL_TOKEN}" \
  -H "X-KArchitect-User: operations" \
  http://127.0.0.1:18347/health | jq .
```
