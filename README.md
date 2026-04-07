# VPN SaaS（Flask + SQLite + 3X-UI）

面向订阅制 VPN 的最小可用产品：**用户注册/登录**、**调用 3X-UI 面板 API 创建/更新 VLESS 客户端**、**多节点切换**、**套餐与流量包（叠加规则）**、**支付宝人工审核订单 + 管理后台确认收款后开通**。

---

## 目录

- [架构与数据流](#架构与数据流)
- [「线路 / 节点」是什么](#线路--节点是什么)
- [项目结构](#项目结构)
- [环境变量说明](#环境变量说明)
- [本地开发启动](#本地开发启动)
- [公网服务器部署](#公网服务器部署)
- [前端页面一览](#前端页面一览)
- [HTTP API 参考](#http-api-参考)
- [管理员与订单流程](#管理员与订单流程)
- [与 3X-UI 的对接](#与-3x-ui-的对接)
- [数据库与备份](#数据库与备份)
- [常见问题与排查](#常见问题与排查)
- [安全与合规提示](#安全与合规提示)

---

## 架构与数据流

```text
用户浏览器
    → Flask（本仓库：页面 + JSON API）
        → SQLite（用户、节点、套餐、订阅、支付订单）
        → 3X-UI 面板 HTTP API（按「当前节点」连接对应面板：建用户、改流量、读用量）
```

- **鉴权**：用户接口使用 **JWT**（`Authorization: Bearer <token>`），登录/注册后由前端存入 `localStorage`。
- **实时用量**：控制台「X-UI 实时用量」来自面板 `getClientTraffics`；失败时用库内订阅做降级展示。
- **订单**：用户在 `/checkout` 提交支付宝订单号 → 库内 `waiting` → 管理员在 `/admin/orders`「确认收款」→ 服务端写 X-UI 并标记 `completed`。

---

## 「线路 / 节点」是什么

在本项目中，**一条「线路」对应数据库里的一条 `Node`（节点）**：

| 概念 | 说明 |
|------|------|
| **节点** | 一条记录包含：该线路对应的 **3X-UI 面板地址**、登录账号、**入站 ID**、`public_host`（生成给用户看的连接域名/IP）等。 |
| **用户当前节点** | `users.current_node_id`；控制台里「切换节点」会改这个字段，并在目标面板上为用户创建客户端（若尚未在该节点出现过）。 |
| **多地区** | `region` 字段用于展示（如 SG、JP），名称自定义（如 `SG-1`）。 |
| **初始化来源** | ① `NODES_JSON`（表为空时导入多条）；② 若未配置 JSON，则用 **单节点** 环境变量 `XUI_BASE_URL` 等生成一条默认节点（见 `app/services/node_service.py`）。 |

**注意**：每个节点应指向 **独立的 3X-UI 实例**（或同一机器不同端口），且用户邮箱在各面板中用于识别客户端；切换节点会在**新面板**上 `addClient`。

---

## 项目结构

```text
.
├── app/
│   ├── __init__.py          # 应用工厂、蓝图注册、全局异常（API 返回 JSON）
│   ├── config.py            # 配置项（从环境变量读取）
│   ├── models.py            # User / Node / Plan / Subscription / PaymentOrder 等
│   ├── routes/              # auth, nodes, plans, pages, admin
│   ├── services/            # xui_client, subscription_provisioning, checkout_catalog, node_service …
│   ├── static/js/           # 落地页联系弹窗、管理端脚本等
│   └── utils/auth_guard.py  # JWT 校验
├── templates/               # Jinja2 页面（勿用 Live Server 直接打开 HTML）
├── deploy/                  # systemd、nginx 示例、rsync、XUI 说明
├── run.py                   # 开发入口：默认 0.0.0.0:5001（可用环境变量改）
├── requirements.txt
├── .env.example             # 环境变量模板（复制为 .env 再改）
└── README.md
```

---

## 环境变量说明

复制 `.env.example` 为 `.env` 后按需修改。核心项如下：

| 变量 | 作用 |
|------|------|
| `SECRET_KEY` | Flask 密钥，务必改为随机长字符串。 |
| `JWT_EXPIRES_HOURS` | JWT 有效期（小时）。 |
| `DATABASE_URL` | 默认 `sqlite:///app.db`（相对项目工作目录）。生产可换 PostgreSQL 等。 |
| `DEPLOY_TAG` | 可选；设置后控制台页脚显示，用于确认 VPS 是否已部署最新代码。 |
| `AUTH_PAGE_BASE_URL` | 可选；落地页若托管在别处时，把登录链接指到本应用根 URL（无尾斜杠）。整站由 Flask 提供时可留空。 |
| `XUI_BASE_URL` | 3X-UI 面板根地址（与浏览器地址栏一致）。可写完整根含 Web 路径，或只写 `http://ip:port` 并配合 `XUI_WEB_BASE_PATH`。 |
| `XUI_WEB_BASE_PATH` | 面板「面板设置」中的 Web 基础路径，以 `/` 开头。 |
| `XUI_USERNAME` / `XUI_PASSWORD` | 面板登录（用于 API）。 |
| `XUI_INBOUND_ID` | 要挂载客户端的入站 ID。 |
| `XUI_VERIFY_SSL` | 自签证书时可设 `false`。 |
| `XUI_PUBLIC_HOST` | 可选；生成 VLESS 时强制使用的对外 Host。 |
| `XUI_CLIENT_LIMIT_IP` | 写入客户端的 `limitIp`（面板「IP 限制」）；`0` 表示不限制。 |
| `NODES_JSON` | 可选；**仅在 `nodes` 表为空时**用于批量创建节点，JSON 数组，字段见下表。 |
| `ADMIN_TOKEN` | **非空**才启用 `/api/admin/orders*`；与请求头 `X-Admin-Token` 一致。 |

`NODES_JSON` 单条对象常用字段示例：

- `name`, `region`, `base_url`, `username`, `password`, `inbound_id`, `verify_ssl`, `public_host`
- 可选：`web_base_path`（单节点覆盖全局 `XUI_WEB_BASE_PATH`）、`is_enabled`

---

## 本地开发启动

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：至少配置可连上的 3X-UI（或先填 NODES_JSON / 单节点变量）
```

运行：

```bash
python run.py
```

- 默认监听 **`0.0.0.0:5001`**（局域网可访问）。
- 覆盖方式：`HOST=127.0.0.1 PORT=5001 python run.py`

本机访问示例：

- 落地页：<http://127.0.0.1:5001/>
- 登录/注册：<http://127.0.0.1:5001/login>
- 控制台：<http://127.0.0.1:5001/dashboard>
- 订单管理：<http://127.0.0.1:5001/admin/orders>（需配置 `ADMIN_TOKEN` 并在页面保存令牌）

**不要用 VS Code Live Server 直接打开 `templates/*.html`**：Jinja 未渲染、`api-base` 等会错误。

---

## 公网服务器部署

### 1. 代码与依赖

将代码放到如 `/opt/vpn-saas`，创建虚拟环境并安装 `requirements.txt`，在服务器上单独维护一份 **`.env`**（勿把本机 `.env` 提交到 Git）。

### 2. systemd（示例）

仓库内参考：`deploy/flask-vps.service.example`

要点：

- `WorkingDirectory` 指向项目根
- `EnvironmentFile=-/opt/vpn-saas/.env`
- `ExecStart` 使用虚拟环境里的 `python run.py`
- 已设 `HOST=0.0.0.0`、`PORT=5001` 便于反代

```bash
sudo cp deploy/flask-vps.service.example /etc/systemd/system/flask-vpn.service
sudo systemctl daemon-reload
sudo systemctl enable --now flask-vpn
sudo systemctl status flask-vpn --no-pager
```

### 3. Nginx 反代

见 **`deploy/nginx-proxy.example.conf`**。**务必把完整 URI 传给上游**（`proxy_pass` 末尾不要随意加路径），否则 `POST /api/auth/login`、`POST /api/plans/checkout-order` 等可能变成 `POST /`，返回 HTML 405/500，前端会误解析。

### 4. 从本机同步到 VPS

`deploy/rsync_to_vps.sh`：默认排除 `.env`、`*.db`、虚拟环境目录等，避免覆盖线上密钥与数据库。可选 `RSYNC_HOST`、`RSYNC_DEST`、`RSYNC_RESTART_SERVICE=1`。

### 5. 管理后台与数据「同源」

用户在 **公网域名** 提交的订单，写入的是 **该服务器上的数据库**。若在 **`http://127.0.0.1:5001/admin/orders`** 打开管理页（本机开发进程），看到的是 **本机库**，**不会**出现 VPS 上的订单。审核订单请使用 **与用户结账相同的站点** 打开 `/admin/orders`。

---

## 前端页面一览

| 路径 | 说明 |
|------|------|
| `/` | 营销落地页 |
| `/login` | 登录 / 注册（`index.html`） |
| `/dashboard` | 用户控制台：套餐摘要、节点、X-UI 用量、订阅链接、升级/流量包入口 |
| `/checkout` | 套餐结账（需登录，JWT） |
| `/recharge` | 流量包结账 |
| `/qr/<file>.png` | 收款二维码静态图，文件名规则见 `pages.py` |
| `/admin/orders` | 订单审核（令牌存浏览器 `localStorage`） |
| `/admin` | 301/302 到 `/admin/orders` |
| `/api/health` | JSON 健康检查（用于确认反代是否打到本应用） |

---

## HTTP API 参考

除特别说明外，JSON 接口统一形如：`{"success": true/false, "message": "...", "data": {...}}`。

### 健康检查

| 方法 | 路径 | 鉴权 |
|------|------|------|
| GET | `/api/health` | 无 |

### 认证（前缀 `/api/auth`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/auth/selftest` | 无 | 部署排查：数据库/BCrypt/JWT 自检 |
| POST | `/api/auth/register` | 无 | Body: `username`, `email`, `password`（≥6 位）；在**第一个可用节点**对应面板创建 VLESS |
| POST | `/api/auth/login` | 无 | Body: `identity`（用户名或邮箱）, `password` |
| GET | `/api/auth/me` | JWT | 返回用户资料、`has_active_plan`、`current_plan`（含 `summary` 等展示字段） |

### 节点（前缀 `/api/nodes`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/nodes` | JWT | 列出启用节点及是否已有该用户访问记录 |
| POST | `/api/nodes/select` | JWT | Body: `node_id`；切换当前节点，必要时在新面板 `addClient` |

### 套餐（前缀 `/api/plans`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/plans` | 无 | 列出启用套餐（`id`, `name`, `price`, `traffic_limit_gb`, `duration_days`） |
| GET | `/api/plans/xui-status` | JWT | 当前用户在本节点对应面板的流量/到期等；`available: false` 时带 `local_fallback` |
| POST | `/api/plans/recharge` | JWT | Body: `traffic_gb` — 叠加流量，**不改变**到期时间 |
| POST | `/api/plans/checkout-order` | JWT | 人工审核订单，见下节 |
| POST | `/api/plans/upgrade` | JWT | Body: `plan_id` — **覆盖**套餐：重置流量并更新到期（按业务逻辑写面板） |

**`POST /api/plans/checkout-order`** Body 示例字段：

- `tier`：`starter` | `standard` | `pro`
- `period`：`weekly` | `monthly` | `quarterly` | `half` | `yearly`
- `trade_no`：支付宝交易号，**16～28 位纯数字**（与前端、账单一致）
- `amount`：必须与服务器价目表一致（`app/services/checkout_catalog.py`），否则返回 400

不再使用单独的「系统订单号」；库内 `public_order_id` 与 `trade_no` 一致，便于唯一约束与核对。

成功后在库中插入 `payment_orders`，`status=waiting`。

---

## 管理员与订单流程

### 鉴权

- 请求头：`X-Admin-Token: <与 .env 中 ADMIN_TOKEN 一致>`
- `.env` 中 `ADMIN_TOKEN` **留空**时，管理订单接口不可用（避免误暴露）。

### 接口（前缀 `/api/admin`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/orders` | 最近约 300 条支付订单摘要 |
| POST | `/api/admin/orders/<id>/confirm` | 确认收款：调用开通逻辑写 X-UI，订单变 `completed` |

浏览器在 **`/admin/orders`** 页面保存令牌后，由 `app/static/js/admin_api.js` 自动附加请求头。

---

## 与 3X-UI 的对接

更细的 URL、叠加规则见 **`deploy/XUI_PROVISIONING.md`**。实现上主要使用（随 3X-UI 版本可能变化，以你面板为准）：

- `POST .../addClient` — 新用户
- `POST .../updateClient/{uuid}` — 更新限额/到期
- `GET .../getClientTraffics/...` — 控制台用量

若面板 API 路径与仓库内 `app/services/xui_client.py` 不一致，需自行对照面板版本改客户端代码。

---

## 数据库与备份

- 默认 **SQLite** 文件在工作目录下的 `app.db`（由 `DATABASE_URL` 决定）。
- 重要表：`users`, `nodes`, `plans`, `subscriptions`, `payment_orders`, `user_node_accesses`。
- **备份**：定期复制 `app.db`（或dump SQL）；部署脚本 `rsync` 默认 **排除** `*.db`，避免覆盖生产库。
- 启动时会 `create_all` 并做轻量 schema 兼容（`db_bootstrap`）；套餐种子见 `plan_service`。

---

## 常见问题与排查

1. **登录/结账返回一大段 HTML**  
   多为 Nginx 把 `/api/...` 转成了错误路径；对照 `deploy/nginx-proxy.example.conf` 检查 `proxy_pass`。

2. **公网下单，本机 `127.0.0.1` 管理页看不到订单**  
   不是 bug：两套进程、两个数据库。请用公网同一站点打开 `/admin/orders`。

3. **管理接口 403（刷新订单列表失败）**  
   表示**服务端** `ADMIN_TOKEN` 为空：浏览器里即使已「保存令牌」也会 403。在 **VPS 项目根** 编辑 `.env` 增加一行，例如 `ADMIN_TOKEN=请改为长随机字符串`，保存后执行 `sudo systemctl restart flask-vpn`（或你的进程名）。确认 `systemctl cat flask-vpn` 里含 `EnvironmentFile=-/opt/vpn-saas/.env` 且 `WorkingDirectory` 指向含 `.env` 的目录。进程启动日志中若见 `ADMIN_TOKEN 未设置` 警告，说明当前进程仍未读到该变量。

4. **注册 502**  
   无法连面板或入站 ID 错误；检查 `XUI_*`、防火墙、面板账号权限。

5. **控制台一直「未开通」**  
   面板快照 `total=0` 与库内订阅不一致时，后端会尝试用订阅兜底；仍异常时查 `subscriptions` 与最近一次 `payment_orders`。

6. **`DEPLOY_TAG` 已改但页面旧**  
   强刷缓存；确认 systemd 已重启且 rsync 未因脚本错误导致文件不完整。

---

## 安全与合规提示

- **切勿**将 `.env`、`*.db`、真实 `ADMIN_TOKEN` 提交到公开仓库。
- JWT 仅防一般越权；管理令牌等价于高危操作权限，请高强度随机、仅限可信环境使用。
- VPN 业务在部分地区受监管，请自行遵守当地法律与服务商政策；本仓库仅为技术示例，不构成法律建议。

---

## 附录：快速 cURL 示例

```bash
BASE=http://127.0.0.1:5001

# 注册
curl -sS -X POST "$BASE/api/auth/register" -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"12345678"}'

# 登录
curl -sS -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"identity":"alice","password":"12345678"}'

# 当前用户（替换 TOKEN）
curl -sS "$BASE/api/auth/me" -H "Authorization: Bearer TOKEN"

# 节点列表
curl -sS "$BASE/api/nodes" -H "Authorization: Bearer TOKEN"

# 套餐列表（无需 JWT）
curl -sS "$BASE/api/plans"
```

---

如有新功能（新环境变量、新 API），请同步更新本 README 与 `.env.example`。
