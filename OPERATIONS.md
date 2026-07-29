# Operations

## Service

- Unit: `karchitect.service`
- Working directory: `/home/kojima/work/karchitect`
- Bind: `127.0.0.1:18347`
- Model: `gemma4:12b-it-qat`
- Ollama: `http://127.0.0.1:11434`

## Checks

```bash
systemctl --user status karchitect.service
curl -fsS http://127.0.0.1:18347/health | jq .
journalctl --user -u karchitect.service -n 100 --no-pager
```

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
curl -fsS http://127.0.0.1:18347/health | jq .
```

