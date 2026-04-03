#!/usr/bin/env bash
# 本机项目 -> VPS（排除 .env、数据库、虚拟环境）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${RSYNC_HOST:-root@139.180.136.98}"
DEST="${RSYNC_DEST:-/opt/vpn-saas}"

echo "==> $ROOT -> $HOST:$DEST"
rsync -avz --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'instance/' \
  --exclude '.env' \
  --exclude '.cursor/' \
  --exclude '.DS_Store' \
  "$ROOT/" "$HOST:$DEST/"

echo "==> 完成"
