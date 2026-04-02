#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/vpn-saas}"

echo "[1/5] 安装 Flask systemd 服务"
sudo cp "$APP_DIR/deploy/flask-vps.service.example" /etc/systemd/system/flask-vpn.service

echo "[2/5] 安装 xray shipper systemd 服务"
sudo cp "$APP_DIR/deploy/xray-online-shipper.service.example" /etc/systemd/system/xray-online-shipper.service

echo "[3/5] 重新加载 systemd"
sudo systemctl daemon-reload

echo "[4/5] 启动并设置开机自启"
sudo systemctl enable --now flask-vpn
sudo systemctl enable --now xray-online-shipper

echo "[5/5] 服务状态"
sudo systemctl --no-pager --full status flask-vpn | sed -n '1,20p'
echo "----------------------------------------"
sudo systemctl --no-pager --full status xray-online-shipper | sed -n '1,20p'

echo "完成。若 xray-online-shipper 启动失败，请先修改："
echo "  /etc/systemd/system/xray-online-shipper.service"
echo "里的 ONLINE_INGEST_KEY 与 Flask .env 保持一致。"
