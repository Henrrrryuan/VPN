# VPN SaaS MVP (Flask + SQLite + x-ui)

This is a stage-1/2 MVP backend for:
- User register/login
- Auto UUID provisioning
- Auto calling x-ui API to create VLESS user
- Returning token + VLESS/subscription info
- JWT protected profile API + simple dashboard page
- Multi-node support (SG/JP) with user node switching
- Plans + subscriptions (套餐 / 购买记录)

## Project structure

```txt
.
├── app
│   ├── routes (auth, nodes, plans, pages)
│   ├── services (auth_service, xui_client, node_service, plan_service, db_bootstrap)
│   ├── models.py
│   └── static/js/landing/contact.js
├── templates (landing.html, index.html, dashboard.html, _site_urls.html)
├── deploy/schema.sql
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
- `XUI_CLIENT_LIMIT_IP`: 写入 3X-UI 客户端的 `limitIp`（面板侧「IP 限制」），与已移除的仪表盘「同时在线人数」统计无关；默认 `2`，`0` 表示不限制

4. Run app:

```bash
python run.py
```

`python run.py` defaults to `http://127.0.0.1:5001` (override with `PORT`).

## API examples

### Register

```bash
curl -X POST http://127.0.0.1:5001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username":"alice",
    "email":"alice@example.com",
    "password":"12345678"
  }'
```

### Login

```bash
curl -X POST http://127.0.0.1:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "identity":"alice",
    "password":"12345678"
  }'
```

### Get current user profile (`/api/auth/me`)

```bash
curl http://127.0.0.1:5001/api/auth/me \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### List enabled nodes

```bash
curl http://127.0.0.1:5001/api/nodes \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### Switch node

```bash
curl -X POST http://127.0.0.1:5001/api/nodes/select \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{"node_id": 2}'
```

## Pages

- `/` marketing landing
- `/login` login / register
- `/dashboard` user panel (JWT in `localStorage`; nodes + plans)

### Plans API

```bash
curl http://127.0.0.1:5001/api/plans
curl http://127.0.0.1:5001/api/plans/subscriptions -H "Authorization: Bearer <TOKEN>"
curl -X POST http://127.0.0.1:5001/api/plans/purchase \
  -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" \
  -d '{"plan_id": 1}'
```

## Notes

- SQLite is enough for MVP. Move to MySQL/PostgreSQL later.
- In some x-ui versions, direct subscription URL may not be returned by `getClientTraffics`. This project now falls back to building a standard VLESS Reality link from inbound config.

## 把 Flask 部署到 VPS（推荐）

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
# 按你的真实信息填写 .env（XUI_*、NODES_JSON 等）
```

### 3) 用 systemd 托管 Flask

仓库里已提供模板：`deploy/flask-vps.service.example`，也可使用 `deploy/install_vps_services.sh` 仅安装 Flask 服务：

```bash
sudo cp /opt/vpn-saas/deploy/flask-vps.service.example /etc/systemd/system/flask-vpn.service
sudo systemctl daemon-reload
sudo systemctl enable --now flask-vpn
sudo systemctl status flask-vpn --no-pager
```

### 4) 验证

```bash
curl -sS http://127.0.0.1:5001/
```

若浏览器里 `/dashboard` 仍是旧版界面，请用 **Mac rsync 同步整个项目**（含 `templates/`）后执行 `sudo systemctl restart flask-vpn`，并 **强制刷新**（Ctrl+F5 / 清空缓存）。
