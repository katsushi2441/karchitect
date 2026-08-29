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
`format`（JSON Schema）を受け付けない。karchitect は短い会話文と変更差分だけを返す
構造化出力 `ChatTurnDelta` が前提で、`format` を落とすと応答が自由文になり解析に失敗する。
完全な `Requirements` はLLMに再出力させず、Python側で差分を既存要件へ統合する。

## 設計ポリシーチェック

`app/policies.py` は、外部LLMのトークン消費・費用削減を目的に含むプロジェクトで、
実行時のClaude/OpenAI依存や実行場所未定義のLLM/VLM利用をコードで検出する。
検出結果はAPIの `design_warnings`、Web画面、設計書へ表示し、Gemmaへ渡す最優先制約にも
利用する。判定はLLMへ委ねず、通常プログラム、ルール、OSS、ローカルモデルを優先する。

AI利用案があるのに有料AIの方針が未確定の場合、`policy_question` で利用者へ先に
「使わない / 利用を許可」を確認し、回答まではLLMへ設計を進めさせない。回答はLLMを
呼ばずPythonで `decisions` と `constraints` へ保存する。「使わない」場合は、既存の
未確認LLM仮定・外部AI連携を除去し、機能要件中のAI処理をローカルモデル表記へ統一する。

## LLM呼び出し前の入力判定

`app/input_guard.py` はGPUを使わず、入力を次のように分類する。

- `続き` / `まだ続く` / `入力中`: `raw_notes`へ保存するだけでLLMを呼ばない
- `入力完了`: 蓄積済みの入力を1回だけLLMで整理する
- 不適切な短答、重複入力: 理由を画面へ返し、LLMを呼ばない
- 確認質問への有効な「はい」「いいえ」: 通常の対話として処理する

AIの質問は1回1問に限定する。`app/response_quality.py` は「以下」の後続欠落、宣言した
項目数の不足、複数質問を保存前に検出し、再生成せず短い応答へ整形する。

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
