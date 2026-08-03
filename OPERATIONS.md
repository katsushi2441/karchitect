# Operations

## Service

- Unit: `karchitect.service`
- Working directory: `/home/kojima/work/karchitect`
- Bind: `0.0.0.0:18347`（内部トークン必須）
- Model: `gemma4:12b-it-qat`
- Ollama: RQDB4AI キュー経由（`192.168.0.14`）。未設定時のみ `http://127.0.0.1:11434` 直叩き

## LLM 経路（RQDB4AI キュー）

対話1ターンは RQDB4AI の `ollama-192-168-0-14-web` キューへ投入し、結果を待つ。

| 設定 | 値 |
|---|---|
| `KARCHITECT_RQDB4AI_URL` | `http://127.0.0.1:18300` |
| `KARCHITECT_RQDB4AI_FUNCTION` | `karchitect.jobs.ollama_chat_job` |
| `KARCHITECT_RQDB4AI_WAIT_TIMEOUT` | 1200 秒（待ち行列に並ぶぶん直叩きより長く取る） |
| `KARCHITECT_LLM_TIMEOUT` | 900 秒（直叩き退避時のタイムアウト） |

**なぜキュー経由にしたか**: 直叩き（`127.0.0.1` = `192.168.0.3`）は kcbrain /
kfreqaihl の判断ジョブと GPU 1枚を奪い合う。2026-08-03 15:26 JST に利用者の
設計セッションが最終成果物の生成中に 180 秒でタイムアウトした際、同時間帯に
`/api/generate` が 8 件走っていた（`15:26:25 | 500 | 3m0s | POST "/api/chat"`）。

**キューが使えないときは直叩きへ自動退避する**（`app/llm.py`）。対話を止めない
ためで、退避したことは `logger.warning` に残る。

**ワーカー側の前提（3つ揃わないと 403 や ImportError になる）**

1. `karchitect.jobs.ollama_chat_job` が `RQDB4AI_OPERATE_ENQUEUE_FUNCTIONS` に載っている
   （載っていないと enqueue が **403 Forbidden**。トークンだけでは通らない）
2. `rqdb4ai/run_worker_with_aixec_env.sh` の PYTHONPATH に
   `/home/kojima/work/karchitect` が入っている
3. `192.168.0.14` に `gemma4:12b-it-qat` がある

`scripts/configure_rqdb4ai_access.py` が 1 と 2 を設定する（トークン値は出力しない）。
実行後は `rqdb4ai-api` / `rqdb4ai-web-worker` / `karchitect` を再起動する。

**kgeo のジョブ関数は流用できない。** `kgeo.jobs.ollama_chat_job` は Ollama の
`format`（JSON Schema）を受け付けない。karchitect は構造化出力 `ChatTurnOutput`
が前提で、`format` を落とすと応答が自由文になり解析に失敗する。

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
