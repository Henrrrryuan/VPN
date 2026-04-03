import json

from flask import current_app

from app.extensions import db
from app.models import Node
from app.services.xui_client import merge_xui_base_url


def bootstrap_nodes_if_needed() -> None:
    if Node.query.count() > 0:
        return

    nodes_json = current_app.config.get("NODES_JSON", "")
    created_count = 0
    if nodes_json:
        try:
            items = json.loads(nodes_json)
        except json.JSONDecodeError:
            items = []

        wp_global = current_app.config.get("XUI_WEB_BASE_PATH", "")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_base = item.get("base_url", "")
                wp = item.get("web_base_path") or wp_global
                merged = merge_xui_base_url(raw_base, wp or None)
                node = Node(
                    name=item.get("name", ""),
                    region=item.get("region", ""),
                    base_url=merged,
                    username=item.get("username", ""),
                    password=item.get("password", ""),
                    inbound_id=int(item.get("inbound_id", 1)),
                    verify_ssl=bool(item.get("verify_ssl", True)),
                    public_host=item.get("public_host", ""),
                    is_enabled=bool(item.get("is_enabled", True)),
                )
                if node.name and node.region and node.base_url and node.username and node.password:
                    db.session.add(node)
                    created_count += 1

    # 兼容旧配置：当 NODES_JSON 未提供时，使用旧版单节点环境变量。
    if created_count == 0:
        base_url = merge_xui_base_url(
            current_app.config.get("XUI_BASE_URL", ""),
            current_app.config.get("XUI_WEB_BASE_PATH", ""),
        )
        username = current_app.config.get("XUI_USERNAME", "")
        password = current_app.config.get("XUI_PASSWORD", "")
        if base_url and username and password:
            db.session.add(
                Node(
                    name="DEFAULT-SG",
                    region="SG",
                    base_url=base_url,
                    username=username,
                    password=password,
                    inbound_id=int(current_app.config.get("XUI_INBOUND_ID", 1)),
                    verify_ssl=bool(current_app.config.get("XUI_VERIFY_SSL", True)),
                    public_host=current_app.config.get("XUI_PUBLIC_HOST", ""),
                    is_enabled=True,
                )
            )

    db.session.commit()
