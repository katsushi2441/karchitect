# Kurage Architect

対話から、実装できる設計書へ。

Kurage Architect (`karchitect`) は、ローカルの Gemma 4 12B と相談しながら、
曖昧なアイデアを要件JSONとシステム設計書へ育てるオープンソースの設計スタジオです。

## 主な機能

- AIがユーザーの質問へ回答しながら、不足情報を1〜3問ずつ確認
- 確定事項・提案・仮定・未決事項を分離した要件JSON
- `discover → clarify → specify → plan → design → review → ready` の仕様駆動フロー
- 機能要件、非機能要件、受入条件、データ、外部連携、リスクの継続更新
- Markdown、要件JSON、Mermaid、HTML、PDF出力
- Gemma 4 12BをOllama経由でローカル実行
- LLM障害時もユーザー回答を失わないフォールバック保存

## OSS統合

`vendor/`には固定コミットのGitサブモジュールとして次を配置しています。

- MetaGPT: PRD、優先順位、設計工程
- GitHub Spec Kit: 仕様化、明確化、計画、レビュー工程
- GPT Engineer: 一問ずつ確認するclarifyパターン

本体はこれらの実行時ライブラリには依存しません。ライセンスと参照元は
[THIRD_PARTY.md](THIRD_PARTY.md)を参照してください。

## 起動

```bash
git clone --recurse-submodules https://github.com/katsushi2441/karchitect.git
cd karchitect
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18347
```

ブラウザで `http://127.0.0.1:18347/` を開きます。

Ollamaには次のモデルが必要です。

```bash
ollama pull gemma4:12b-it-qat
```

Gemma 4は思考型モデルのため、Kurage ArchitectはOllama APIへ必ず
`"think": false`を指定します。

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | API・Ollama・モデル状態 |
| GET/POST | `/api/projects` | プロジェクト一覧・作成 |
| GET | `/api/projects/{id}` | 会話・要件・設計書取得 |
| POST | `/api/projects/{id}/messages` | 設計相談 |
| PUT | `/api/projects/{id}/requirements` | 要件JSONの手動更新 |
| GET | `/api/projects/{id}/document.md` | Markdown |
| GET | `/api/projects/{id}/requirements.json` | 要件JSON |
| GET | `/api/projects/{id}/document.pdf` | PDF |
| GET | `/api/projects/{id}/mermaid/{diagram}` | Mermaidソース |

## 公開Web版

`https://kurage.exbridge.jp/karchitect.php` では、Kurage共通のX認証で誰でも利用できます。
PHPゲートウェイが認証済みXユーザー名と内部トークンをAPIへ渡し、プロジェクトは
ユーザー単位で分離されます。ブラウザへAPIトークンを公開しません。

公開に必要な設定は `.env.example` と
`public/karchitect_config.php.example` を参照してください。秘密値を設定後、
`scripts/deploy.sh` でPHP・UI・MermaidアセットをFTP配備します。

## データ

既定では`data/karchitect.db`へSQLite形式で保存します。会話履歴だけに依存せず、
各ターンでPydantic検証済みの完全な要件JSONを保存します。

## テスト

```bash
.venv/bin/pytest -q
```

## ライセンス

MIT
