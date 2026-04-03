#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/vpn-saas}"

echo "[1/3] 安装 Flask systemd 服务"
sudo cp "$APP_DIR/deploy/flask-vps.service.example" /etc/systemd/system/flask-vpn.service

echo "[2/3] 重新加载 systemd"
sudo systemctl daemon-reload

echo "[3/3] 启动并设置开机自启"
sudo systemctl enable --now flask-vpn

echo "服务状态"
sudo systemctl --no-pager --full status flask-vpn | sed -n '1,20p'

echo "完成。"
