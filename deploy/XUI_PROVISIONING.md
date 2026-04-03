# 套餐与 3X-UI 对接说明

实现依据 [3x-ui](https://github.com/MHSanaei/3x-ui) 当前主分支路由：

- `POST /panel/api/inbounds/addClient` — 新建客户端（尚无 UUID 时）
- `POST /panel/api/inbounds/updateClient/{clientUuid}` — 更新已有客户端（已注册用户购买套餐）
- `GET /panel/api/inbounds/getClientTraffics/{email}` — 实时流量/限额（控制台「X-UI 实时用量」与叠加计算用）
- 入站 JSON 中 `totalGB` 使用**字节**；`expiryTime` 为 **Unix 毫秒**。

## 叠加规则（每次购买）

- **到期**：`new_expiry = max(现在, 当前面板到期) + 本单天数`（若当前无到期则从现在起算）。
- **流量上限**：`new_total_bytes = 面板当前 total（字节）+ 本单套餐 GB 对应字节`；若当前为 0（不限）则只设为本单流量。

## 用户端展示

- 以 **`GET /api/plans/xui-status`**（JWT）为准，数据来自面板，与 `getClientTraffics` 一致。

若购买接口返回 502，请记录：**面板版本号**、浏览器 F12 中同一入站手动改限额是否成功。若你的分支 API 路径不同，再改 `app/services/xui_client.py` 中的 URL。
