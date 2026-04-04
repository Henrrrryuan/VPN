#!/usr/bin/env bash
# 本机项目 -> VPS（排除 .env、数据库、虚拟环境）
#
# 重要：rsync 的「行尾 \」续行中间不能插入单独的 # 注释行，否则 bash 会把续行与注释合并，
# 导致从 # 起整段 rsync 参数被吃掉，后面的 --exclude 会变成「独立命令」执行失败，
# 表现为同步不完整、VPS 仍是旧版页面与接口。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${RSYNC_HOST:-root@139.180.136.98}"
DEST="${RSYNC_DEST:-/opt/vpn-saas}"

echo "==> $ROOT -> $HOST:$DEST"
# 保留线上 SQLite：排除 *.db；--delete 会删远端多余文件，但 *.db 不会被同步覆盖/删除
rsync -avz --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'instance/' \
  --exclude '*.db' \
  --exclude 'data/' \
  --exclude '.env' \
  --exclude '.cursor/' \
  --exclude '.DS_Store' \
  "$ROOT/" "$HOST:$DEST/"

echo "==> 同步完成"

if [[ "${RSYNC_RESTART_SERVICE:-}" == "1" ]]; then
  echo "==> 重启 flask-vpn.service（RSYNC_RESTART_SERVICE=1）"
  ssh "$HOST" "systemctl restart flask-vpn.service && systemctl is-active flask-vpn.service"
fi

if [[ "${RSYNC_VERIFY:-1}" != "0" ]]; then
  echo "==> 远端快速校验（dashboard + /recharge 页面与路由）"
  ssh "$HOST" "set -e; \
    test -f '$DEST/templates/dashboard.html' && grep -q '选择套餐' '$DEST/templates/dashboard.html'; \
    test -f '$DEST/templates/recharge.html'; \
    grep -q 'def recharge_page' '$DEST/app/routes/pages.py'; \
    echo OK: 模板与 pages.py 含 recharge"
fi
