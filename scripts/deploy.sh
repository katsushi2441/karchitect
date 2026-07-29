#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. /home/kojima/work/aixec/.env
set +a

remote="/web/kurage_exbridge_jp"
upload() {
  local source_file="$1"
  local remote_file="$2"
  curl --fail --silent --show-error --ftp-create-dirs -T "$source_file" \
    "ftp://${FTP_USER}:${FTP_PASS}@${FTP_HOST}${remote}/${remote_file}"
  echo "deployed: ${remote_file}"
}

upload public/karchitect.php karchitect.php
upload static/index.html karchitect_app.html
upload static/styles.css assets/karchitect.css
upload static/app.js assets/karchitect.js
upload static/vendor/mermaid.min.js assets/karchitect-mermaid.min.js
if [[ -f public/karchitect_config.php ]]; then
  upload public/karchitect_config.php karchitect_config.php
fi

echo "published: https://kurage.exbridge.jp/karchitect.php"
