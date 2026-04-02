import json
import uuid as uuid_lib
from urllib.parse import quote

import requests

from app.models import Node


class XUIClientError(Exception):
    pass


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
        try:
            from flask import current_app, has_request_context

            if has_request_context():
                limit_ip = int(current_app.config.get("XUI_CLIENT_LIMIT_IP", 2))
        except RuntimeError:
            pass
        return cls(
            base_url=node.base_url,
            username=node.username,
            password=node.password,
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

    def get_client_traffics(self, email: str) -> dict:
        """
        Query x-ui inbound client traffic info by client email.

        Note: x-ui versions vary; this returns exactly what panel provides
        (commonly includes lastOnline/up/down), but may not include
        "online IP count" details.
        """
        self._login()
        from urllib.parse import quote

        sub_url = f"{self.base_url}/panel/api/inbounds/getClientTraffics/{quote(email, safe='')}"
        try:
            traffic_resp = self.session.get(sub_url, timeout=15)
        except requests.RequestException as exc:
            raise XUIClientError(f"x-ui getClientTraffics request failed: {exc}") from exc

        if traffic_resp.status_code != 200:
            raise XUIClientError(f"x-ui getClientTraffics failed with status {traffic_resp.status_code}")

        data = traffic_resp.json()
        if not data.get("success"):
            raise XUIClientError(f"x-ui getClientTraffics error: {data.get('msg', 'unknown error')}")

        return data.get("obj") or {}

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

    def create_vless_user(self, username: str, email: str) -> tuple[str, str]:
        self._login()
        user_uuid = str(uuid_lib.uuid4())

        settings = {
            "clients": [
                {
                    "id": user_uuid,
                    "email": email,
                    "flow": "xtls-rprx-vision",
                    "limitIp": self.limit_ip,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "comment": f"user:{username}",
                    "reset": 0,
                }
            ],
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

        sub_url = f"{self.base_url}/panel/api/inbounds/getClientTraffics/{email}"
        try:
            traffic_resp = self.session.get(sub_url, timeout=15)
        except requests.RequestException:
            traffic_resp = None
        if traffic_resp is not None and traffic_resp.status_code == 200:
            data = traffic_resp.json()
            obj = data.get("obj") or {}
            if obj.get("subscriptionUrl"):
                return user_uuid, obj["subscriptionUrl"]

        # fallback for panel versions not returning subscription URL
        return user_uuid, self._build_vless_link(user_uuid=user_uuid, email=email)
