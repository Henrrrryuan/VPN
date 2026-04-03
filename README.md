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
curl http://127.0.0.1:5001/api/plans/xui-status -H "Authorization: Bearer <TOKEN>"
curl http://127.0.0.1:5001/api/plans/subscriptions -H "Authorization: Bearer <TOKEN>"
curl -X POST http://127.0.0.1:5001/api/plans/purchase \
  -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" \
  -d '{"plan_id": 1}'
```

购买成功后会调用 3X-UI 写入/更新客户端流量与到期时间，并在 JSON 中返回 `subscription_url` 与 `node`（详见 `deploy/XUI_PROVISIONING.md`）。

## Notes

- SQLite is enough for MVP. Move to MySQL/PostgreSQL later.
- In some x-ui versions, direct subscription URL may not be returned by `getClientTraffics`. This project now falls back to building a standard VLESS Reality link from inbound config.

## 把 Flask 部署到 VPS（推荐）

### 1) 上传代码到 VPS

示例路径：`/opt/vpn-saas`

**从本机一键 rsync（需已能 `ssh root@139.180.136.98` 登录）：**

```bash
cd /path/to/VPN   # 项目根目录
chmod +x deploy/rsync_to_vps.sh
./deploy/rsync_to_vps.sh
# 可选环境变量：
#   RSYNC_HOST=root@你的IP RSYNC_DEST=/opt/vpn-saas
#   RSYNC_RESTART_SERVICE=1   # 同步后自动 ssh 执行 systemctl restart flask-vpn.service
#   RSYNC_VERIFY=0            # 跳过脚本末尾的远端 grep 校验（仅 rsync、无 ssh 时）
```

脚本会排除 `.env`、`*.db`、`data/`、`instance/`、`.venv`，避免覆盖线上密钥与数据库。同步结束后会默认 **ssh 到 VPS** 检查 `templates/dashboard.html` 是否包含「选择套餐」；若报错，说明文件未完整同步或路径不是 `/opt/vpn-saas`。

同步完成后请 **重启服务**（或设 `RSYNC_RESTART_SERVICE=1` 自动重启），浏览器再 **强制刷新**。

或手动：

```bash
sudo mkdir -p /opt/vpn-saas
sudo chown -R $USER:$USER /opt/vpn-saas
# git clone / scp / rsync 均可
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

若浏览器里 `/dashboard` 仍是旧版界面：先确认本机 `deploy/rsync_to_vps.sh` 为最新（旧版脚本曾在 `rsync` 续行里插入 `#` 注释，会导致同步不完整）。然后重新执行 rsync、`sudo systemctl restart flask-vpn`，并 **强制刷新**（Ctrl+F5 / 清空缓存）。
