import json
import os
import uuid as uuid_lib
from urllib.parse import quote, urlparse

import requests

from app.models import Node


class XUIClientError(Exception):
    pass


def _env_str_or(key: str, fallback: str) -> str:
    """若进程环境中有该键且非空，用环境值；否则用 fallback（避免只改 .env 未同步 nodes 表）。"""
    raw = os.environ.get(key)
    if raw is None:
        return fallback
    s = str(raw).strip()
    return s if s else fallback


def merge_xui_base_url(node_base: str, web_path_from_config: str | None) -> str:
    """
    将 3X-UI 的 Web 基础路径拼到面板根地址上（无路径时登录会打到错误 URL）。
    node_base 已含路径时不会重复追加。
    """
    root = (node_base or "").rstrip("/")
    if not web_path_from_config or not str(web_path_from_config).strip():
        return root
    ep = str(web_path_from_config).strip().rstrip("/")
    if not ep.startswith("/"):
        ep = "/" + ep
    parsed = urlparse(root)
    cur = (parsed.path or "").rstrip("/")
    want = ep.rstrip("/")
    if cur == want or (cur and cur.endswith(want)):
        return root
    return root + ep


def _traffic_limit_bytes_from_gb(total_gb: float | None) -> int:
    """3X-UI 入站 JSON 中 totalGB 与面板内部一致时使用字节（与 ResetClientTrafficLimitByEmail 一致）。"""
    if total_gb is None or total_gb <= 0:
        return 0
    return int(round(float(total_gb) * 1024 * 1024 * 1024))


class XUIClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        inbound_id: int,
        verify_ssl: bool = True,
        public_host: str = "",
        limit_ip: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.inbound_id = inbound_id
        self.verify_ssl = verify_ssl
        self.public_host = public_host
        self.limit_ip = max(0, int(limit_ip))
        self.session = requests.Session()
        self.session.verify = self.verify_ssl

    @classmethod
    def from_node(cls, node: Node) -> "XUIClient":
        limit_ip = 2
        merged_base = node.base_url
        try:
            from flask import current_app, has_request_context

            if has_request_context():
                limit_ip = int(current_app.config.get("XUI_CLIENT_LIMIT_IP", 2))
                wp = current_app.config.get("XUI_WEB_BASE_PATH")
                merged_base = merge_xui_base_url(node.base_url, wp)
        except RuntimeError:
            pass
        return cls(
            base_url=merged_base,
            username=_env_str_or("XUI_USERNAME", node.username),
            password=_env_str_or("XUI_PASSWORD", node.password),
            inbound_id=node.inbound_id,
            verify_ssl=node.verify_ssl,
            public_host=node.public_host or "",
            limit_ip=limit_ip,
        )

    def _login(self) -> None:
        url = f"{self.base_url}/login"
        payload = {"username": self.username, "password": self.password}
        try:
            response = self.session.post(url, data=payload, timeout=15)
        except requests.RequestException as exc:
            raise XUIClientError(f"x-ui login request failed: {exc}") from exc
        if response.status_code != 200:
            raise XUIClientError(f"x-ui login failed with status {response.status_code}")

    def _traffics_url(self, email: str) -> str:
        safe = quote(str(email), safe="")
        return f"{self.base_url}/panel/api/inbounds/getClientTraffics/{safe}"

    def _traffics_by_id_url(self, client_uuid: str) -> str:
        safe = quote(str(client_uuid), safe="")
        return f"{self.base_url}/panel/api/inbounds/getClientTrafficsById/{safe}"

    @staticmethod
    def _parse_traffic_payload(data: dict) -> dict | None:
        if not data.get("success"):
            return None
        obj = data.get("obj")
        # 3X-UI：有记录时为单个对象；无记录时常为 null（不是空对象）
        if obj is None:
            return None
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if not isinstance(obj, dict):
            return None
        return {
            "total": int(obj.get("total") or 0),
            "up": int(obj.get("up") or 0),
            "down": int(obj.get("down") or 0),
            "allTime": int(obj.get("allTime") or 0),
            "expiryTime": int(obj.get("expiryTime") or 0),
            "subscriptionUrl": obj.get("subscriptionUrl"),
        }

    @staticmethod
    def _normalize_inbounds_list_obj(data: dict) -> list | None:
        """GET /panel/api/inbounds/list 的 obj：常为 inbound 数组；nil 时 JSON 为 null。"""
        if not data.get("success"):
            return None
        raw = data.get("obj")
        if raw is None:
            return []
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, list):
            return raw
        return None

    def _get_traffic_json(self, url: str) -> dict | None:
        try:
            resp = self.session.get(url, timeout=15)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        return self._parse_traffic_payload(data)

    @staticmethod
    def _client_stat_row_to_snapshot(st: dict) -> dict:
        """与 getClientTraffics 返回字段对齐（见 3x-ui xray.ClientTraffic）。"""
        return {
            "total": int(st.get("total") or 0),
            "up": int(st.get("up") or 0),
            "down": int(st.get("down") or 0),
            "allTime": int(st.get("allTime") or 0),
            "expiryTime": int(st.get("expiryTime") or 0),
            "subscriptionUrl": st.get("subscriptionUrl"),
        }

    def _match_client_stat(
        self, rows: list, email: str, client_uuid: str | None
    ) -> dict | None:
        em = str(email).strip().lower()
        uid = (str(client_uuid).strip() if client_uuid else "") or ""
        for st in rows:
            if not isinstance(st, dict):
                continue
            st_email = str(st.get("email") or "").strip().lower()
            st_uuid = str(st.get("uuid") or "").strip()
            if em and st_email == em:
                return self._client_stat_row_to_snapshot(st)
            if uid and st_uuid == uid:
                return self._client_stat_row_to_snapshot(st)
        return None

    def _snapshot_from_inbounds_list(
        self, email: str, client_uuid: str | None
    ) -> dict | None:
        """
        与面板「入站列表」同源：GET /panel/api/inbounds/list，从 clientStats 取数。
        优先当前节点 inbound_id，找不到则全量入站中按邮箱/UUID 匹配。
        """
        url = f"{self.base_url}/panel/api/inbounds/list"
        try:
            resp = self.session.get(url, timeout=20)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        obj = self._normalize_inbounds_list_obj(data)
        if obj is None:
            return None

        preferred: list[dict] = []
        all_rows: list[dict] = []
        for inbound in obj:
            if not isinstance(inbound, dict):
                continue
            stats = inbound.get("clientStats")
            if not isinstance(stats, list):
                continue
            for st in stats:
                if isinstance(st, dict):
                    all_rows.append(st)
            if inbound.get("id") == self.inbound_id:
                for st in stats:
                    if isinstance(st, dict):
                        preferred.append(st)

        hit = self._match_client_stat(preferred, email, client_uuid)
        if hit:
            return hit
        return self._match_client_stat(all_rows, email, client_uuid)

    def get_client_traffic_snapshot(
        self, email: str, client_uuid: str | None = None
    ) -> dict | None:
        """
        优先 GET /panel/api/inbounds/list（与面板「入站列表」同源，新客户端在 getClientTraffics 下常返回 obj=null）。
        再试 getClientTraffics / getClientTrafficsById。
        返回 total/up/down/allTime/expiryTime/subscriptionUrl（与面板一致，字节级）。
        """
        self._login()
        em = str(email).strip()
        snap = self._snapshot_from_inbounds_list(em, client_uuid)
        if snap is not None:
            return snap
        snap = self._get_traffic_json(self._traffics_url(em))
        if snap is None and em.lower() != em:
            snap = self._get_traffic_json(self._traffics_url(em.lower()))
        if snap is None and client_uuid:
            snap = self._get_traffic_json(self._traffics_by_id_url(client_uuid))
        return snap

    def _resolve_subscription_link(self, email: str, user_uuid: str) -> str:
        sub_url = self._traffics_url(email)
        try:
            traffic_resp = self.session.get(sub_url, timeout=15)
        except requests.RequestException:
            traffic_resp = None
        if traffic_resp is not None and traffic_resp.status_code == 200:
            data = traffic_resp.json()
            obj = data.get("obj") or {}
            if obj.get("subscriptionUrl"):
                return str(obj["subscriptionUrl"])
        return self._build_vless_link(user_uuid=user_uuid, email=email)

    def _build_vless_link(self, user_uuid: str, email: str) -> str:
        get_url = f"{self.base_url}/panel/api/inbounds/get/{self.inbound_id}"
        try:
            response = self.session.get(get_url, timeout=15)
        except requests.RequestException:
            return ""
        if response.status_code != 200:
            return ""

        result = response.json()
        if not result.get("success"):
            return ""

        obj = result.get("obj") or {}
        port = obj.get("port")
        remark = obj.get("remark") or "VPN"

        stream_settings = obj.get("streamSettings")
        if isinstance(stream_settings, str):
            try:
                stream_settings = json.loads(stream_settings or "{}")
            except json.JSONDecodeError:
                stream_settings = {}
        stream_settings = stream_settings or {}

        reality_settings = stream_settings.get("realitySettings") or {}
        reality_client_settings = reality_settings.get("settings") or {}
        settings = obj.get("settings")
        if isinstance(settings, str):
            try:
                settings = json.loads(settings or "{}")
            except json.JSONDecodeError:
                settings = {}
        settings = settings or {}

        host = self.public_host or obj.get("listen") or ""
        if not host or host == "0.0.0.0":
            host = self.base_url.split("://", 1)[-1].split(":", 1)[0]

        sni = ""
        server_names = reality_settings.get("serverNames") or []
        if server_names:
            sni = server_names[0]

        pbk = reality_settings.get("publicKey", "") or reality_client_settings.get("publicKey", "")
        short_ids = reality_settings.get("shortIds") or [""]
        sid = short_ids[0] if short_ids else ""
        fp = reality_client_settings.get("fingerprint", "") or "chrome"

        params = (
            f"encryption=none&flow=xtls-rprx-vision&security=reality"
            f"&sni={quote(sni)}&fp={quote(fp)}&pbk={quote(pbk)}&sid={quote(sid)}"
            f"&type=tcp&headerType=none"
        )
        return f"vless://{user_uuid}@{host}:{port}?{params}#{quote(f'{remark}-{email}')}"

    def _client_dict(
        self,
        user_uuid: str,
        email: str,
        username: str,
        total_bytes: int,
        expiry_time_ms: int,
    ) -> dict:
        return {
            "id": user_uuid,
            "email": email,
            "flow": "xtls-rprx-vision",
            "limitIp": self.limit_ip,
            "totalGB": total_bytes,
            "expiryTime": int(expiry_time_ms),
            "enable": True,
            "tgId": "",
            "subId": "",
            "comment": f"user:{username}",
            "reset": 0,
        }

    def create_vless_user(
        self,
        username: str,
        email: str,
        *,
        total_gb: float | None = None,
        expiry_time_ms: int | None = None,
    ) -> tuple[str, str]:
        """创建入站客户端。total_gb / expiry_time_ms 默认 0 表示不限制（与面板一致）。"""
        self._login()
        user_uuid = str(uuid_lib.uuid4())
        total_bytes = _traffic_limit_bytes_from_gb(total_gb)
        exp_ms = 0 if expiry_time_ms is None else int(expiry_time_ms)

        settings = {
            "clients": [self._client_dict(user_uuid, email, username, total_bytes, exp_ms)],
            "decryption": "none",
            "fallbacks": [],
        }
        payload = {"id": self.inbound_id, "settings": json.dumps(settings)}

        add_url = f"{self.base_url}/panel/api/inbounds/addClient"
        try:
            response = self.session.post(add_url, data=payload, timeout=15)
        except requests.RequestException as exc:
            raise XUIClientError(f"x-ui addClient request failed: {exc}") from exc
        if response.status_code != 200:
            raise XUIClientError(f"x-ui addClient failed with status {response.status_code}")

        result = response.json()
        if not result.get("success"):
            raise XUIClientError(f"x-ui addClient error: {result.get('msg', 'unknown error')}")

        return user_uuid, self._resolve_subscription_link(email, user_uuid)

    def update_client_quota_raw(
        self,
        client_uuid: str,
        username: str,
        email: str,
        total_bytes: int,
        expiry_time_ms: int,
    ) -> str:
        """直接以字节更新客户端总流量上限与到期时间（叠加后的最终值）。"""
        self._login()
        tb = max(0, int(total_bytes))
        settings = {
            "clients": [
                self._client_dict(
                    client_uuid,
                    email,
                    username,
                    tb,
                    int(expiry_time_ms),
                )
            ],
            "decryption": "none",
            "fallbacks": [],
        }
        payload = {"id": self.inbound_id, "settings": json.dumps(settings)}
        url = f"{self.base_url}/panel/api/inbounds/updateClient/{client_uuid}"
        try:
            response = self.session.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            raise XUIClientError(f"x-ui updateClient request failed: {exc}") from exc
        if response.status_code != 200:
            raise XUIClientError(f"x-ui updateClient failed with status {response.status_code}")

        result = response.json()
        if not result.get("success"):
            raise XUIClientError(f"x-ui updateClient error: {result.get('msg', 'unknown error')}")

        return self._resolve_subscription_link(email, client_uuid)

    def update_client_quota(
        self,
        client_uuid: str,
        username: str,
        email: str,
        total_gb: float,
        expiry_time_ms: int,
    ) -> str:
        """
        更新已有客户端的流量与到期时间（POST /panel/api/inbounds/updateClient/{uuid}）。
        total_gb<=0 视为不限制（totalGB=0）；expiry_time_ms 为 Unix 毫秒时间戳。
        """
        total_bytes = _traffic_limit_bytes_from_gb(total_gb if total_gb and total_gb > 0 else None)
        return self.update_client_quota_raw(
            client_uuid, username, email, total_bytes, expiry_time_ms
        )
