# VPN SaaS MVP (Flask + SQLite + x-ui)

This is a stage-1/2 MVP backend for:
- User register/login
- Auto UUID provisioning
- Auto calling x-ui API to create VLESS user
- Returning token + VLESS/subscription info
- JWT protected profile API + simple dashboard page
- Multi-node support (SG/JP) with user node switching

## Project structure

```txt
.
├── app
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models.py
│   ├── routes
│   │   ├── auth.py
│   │   └── pages.py
│   └── services
│       ├── auth_service.py
│       └── xui_client.py
├── templates
│   ├── dashboard.html
│   └── index.html
├── .env.example
├── requirements.txt
└── run.py
```

## Quick start

1. Create and activate virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure env:

```bash
cp .env.example .env
```

Then edit `.env`:
- `SECRET_KEY`: set a strong random string
- `NODES_JSON`: set at least one node config (recommended with SG + JP)
- `XUI_CLIENT_LIMIT_IP`: max distinct source IPs per client UUID at once in 3X-UI (`limitIp`); default `2`; use `0` for unlimited

4. Run app:

```bash
python run.py
```

Server starts at `http://127.0.0.1:5000`.

## API examples

### Register

```bash
curl -X POST http://127.0.0.1:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username":"alice",
    "email":"alice@example.com",
    "password":"12345678"
  }'
```

### Login

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "identity":"alice",
    "password":"12345678"
  }'
```

### Get current user profile (`/api/auth/me`)

```bash
curl http://127.0.0.1:5000/api/auth/me \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### List enabled nodes

```bash
curl http://127.0.0.1:5000/api/nodes \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### Switch node

```bash
curl -X POST http://127.0.0.1:5000/api/nodes/select \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{"node_id": 2}'
```

## Pages

- `/` login/register page
- `/dashboard` user panel page (reads JWT from browser localStorage, supports node switching)

## Notes

- SQLite is enough for MVP. Move to MySQL/PostgreSQL later.
- In some x-ui versions, direct subscription URL may not be returned by `getClientTraffics`. This project now falls back to building a standard VLESS Reality link from inbound config.

## 精确统计“同时在线 IP 数”（方案A）

仅依赖 3X-UI 的 `getClientTraffics` 通常只能拿到 `lastOnline`，无法精确统计 “同一 UUID 同时在线的不同公网 IP 数”。

本项目支持通过 Xray access log 上报在线事件，进而精确统计：

- 上报接口：`POST /api/online/ingest`（Header：`X-Ingest-Key`）
- 用户侧展示：`/dashboard` 显示 `x/2`；若未接入上报，则会显示 `（估算）`

### 1) 配置 Flask

在 `.env` 里设置：

- `ONLINE_INGEST_KEY`
- `ONLINE_STATS_WINDOW_SEC`（默认 180 秒）

### 2) 节点侧运行采集脚本

将 `scripts/xray_online_shipper.py` 复制到 VPS 节点，确保 Xray 已开启 access log（例如 `/var/log/xray/access.log`），然后运行：

```bash
export FLASK_INGEST_URL="http://<你的Flask地址>:5001/api/online/ingest"
export ONLINE_INGEST_KEY="<与你 .env 一致的密钥>"
export XRAY_ACCESS_LOG="/var/log/xray/access.log"
export NODE_ID="1"
python3 xray_online_shipper.py
```

## 把 Flask 部署到 VPS（推荐）

如果你的 Flask 还跑在本地电脑，VPS 节点无法稳定上报在线事件。推荐把 Flask 部署到同一台 VPS，然后让采集器直接上报 `127.0.0.1`。

### 1) 上传代码到 VPS

示例路径：`/opt/vpn-saas`

```bash
sudo mkdir -p /opt/vpn-saas
sudo chown -R $USER:$USER /opt/vpn-saas
# 把项目文件上传到 /opt/vpn-saas（git clone / scp 均可）
```

### 2) 安装依赖并配置 `.env`

```bash
cd /opt/vpn-saas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 按你的真实信息填写 .env（XUI_*、ONLINE_* 等）
```

### 3) 用 systemd 托管 Flask

仓库里已提供模板：`deploy/flask-vps.service.example`

```bash
sudo cp /opt/vpn-saas/deploy/flask-vps.service.example /etc/systemd/system/flask-vpn.service
sudo systemctl daemon-reload
sudo systemctl enable --now flask-vpn
sudo systemctl status flask-vpn --no-pager
```

### 4) 安装在线采集器（systemd 开机自启）

仓库里已提供：
- `deploy/xray-online-shipper.service.example`
- `deploy/install_vps_services.sh`（一键安装两个服务）

#### 方式 A：一键安装（推荐）

```bash
cd /opt/vpn-saas
chmod +x deploy/install_vps_services.sh
./deploy/install_vps_services.sh /opt/vpn-saas
```

#### 方式 B：手动安装

```bash
sudo cp /opt/vpn-saas/deploy/xray-online-shipper.service.example /etc/systemd/system/xray-online-shipper.service
# 编辑 /etc/systemd/system/xray-online-shipper.service：
# ONLINE_INGEST_KEY 要与 /opt/vpn-saas/.env 中 ONLINE_INGEST_KEY 一致
sudo systemctl daemon-reload
sudo systemctl enable --now xray-online-shipper
sudo systemctl status xray-online-shipper --no-pager
```

### 5) 节点采集器改成本机上报（关键参数）

在 VPS 上运行采集器时，`FLASK_INGEST_URL` 可直接写：

```bash
export FLASK_INGEST_URL="http://127.0.0.1:5001/api/online/ingest"
export ONLINE_INGEST_KEY="<与你 .env 一致的密钥>"
export XRAY_ACCESS_LOG="/var/log/xray/access.log"
export NODE_ID="1"
python3 /opt/vpn-saas/scripts/xray_online_shipper.py
```

> 若使用 `xray-online-shipper.service`，上述环境变量由 service 文件内的 `Environment=` 提供，不需要手工 export。

### 6) 验证

```bash
curl -sS http://127.0.0.1:5001/
curl -sS -X POST http://127.0.0.1:5001/api/online/cleanup \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Key: <与你 .env 一致的密钥>" \
  -d '{"keep_seconds":3600}'
```
