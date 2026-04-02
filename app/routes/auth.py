from datetime import datetime, UTC

from flask import Blueprint, jsonify, request, g, current_app

from app.extensions import bcrypt, db
from app.models import Node, User, UserNodeAccess
from app.services.auth_service import generate_access_token
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required

auth_bp = Blueprint("auth", __name__)


def _validate_register_payload(data: dict) -> tuple[bool, str]:
    required = ["username", "email", "password"]
    for key in required:
        if not data.get(key):
            return False, f"missing field: {key}"
    if len(data["password"]) < 6:
        return False, "password must be at least 6 chars"
    return True, ""


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    ok, msg = _validate_register_payload(data)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    username = data["username"].strip()
    email = data["email"].strip().lower()
    password = data["password"]

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "username already exists"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "email already exists"}), 409

    node = Node.query.filter_by(is_enabled=True).order_by(Node.id.asc()).first()
    if not node:
        return jsonify({"success": False, "message": "no enabled node available"}), 503

    xui = XUIClient.from_node(node)
    try:
        user_uuid, vless_link = xui.create_vless_user(username=username, email=email)
    except XUIClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        uuid=user_uuid,
        vless_link=vless_link,
        current_node_id=node.id,
    )
    db.session.add(user)
    db.session.flush()

    node_access = UserNodeAccess(
        user_id=user.id,
        node_id=node.id,
        uuid=user_uuid,
        vless_link=vless_link,
    )
    db.session.add(node_access)
    db.session.commit()

    token = generate_access_token(user.id)
    return (
        jsonify(
            {
                "success": True,
                "message": "register success",
                "data": {
                    "token": token,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "uuid": user.uuid,
                        "vless_link": user.vless_link,
                        "current_node_id": user.current_node_id,
                    },
                },
            }
        ),
        201,
    )


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    identity = (data.get("identity") or "").strip()
    password = data.get("password") or ""
    if not identity or not password:
        return jsonify({"success": False, "message": "identity and password required"}), 400

    user = User.query.filter((User.username == identity) | (User.email == identity.lower())).first()
    if not user:
        return jsonify({"success": False, "message": "invalid credentials"}), 401

    if not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"success": False, "message": "invalid credentials"}), 401

    token = generate_access_token(user.id)
    return jsonify(
        {
            "success": True,
            "message": "login success",
            "data": {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "uuid": user.uuid,
                    "vless_link": user.vless_link,
                    "current_node_id": user.current_node_id,
                },
            },
        }
    )


@auth_bp.get("/me")
@jwt_required
def me():
    user = g.current_user
    return jsonify(
        {
            "success": True,
            "data": {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "uuid": user.uuid,
                    "vless_link": user.vless_link,
                    "current_node_id": user.current_node_id,
                }
            },
        }
    )


@auth_bp.get("/usage")
@jwt_required
def usage():
    """
    Estimate current concurrent usage based on x-ui's lastOnline.

    x-ui may not expose "online IP count" details; we show an estimate
    using lastOnline time window.
    """
    user = g.current_user
    limit_ip = int(current_app.config.get("XUI_CLIENT_LIMIT_IP", 2))

    if not user.current_node_id:
        return jsonify({"success": False, "message": "current_node_id missing"}), 400

    node = Node.query.get(user.current_node_id)
    if not node:
        return jsonify({"success": False, "message": "node not found"}), 404

    xui = XUIClient.from_node(node)
    try:
        traffics = xui.get_client_traffics(user.email)
    except XUIClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    last_online_ms = traffics.get("lastOnline") or 0
    now_ms = int(datetime.now(UTC).timestamp() * 1000)

    # 如果 lastOnline 在该时间窗内，则视为“在线”。
    window_ms = int(current_app.config.get("USAGE_ONLINE_WINDOW_MS", "120000"))
    online_ip_count = 0
    if last_online_ms:
        try:
            online_ip_count = 1 if (now_ms - int(last_online_ms)) <= window_ms else 0
        except Exception:
            online_ip_count = 0

    return jsonify(
        {
            "success": True,
            "data": {
                "limit_ip": limit_ip,
                "online_ip_count": online_ip_count,
                "online_window_sec": int(window_ms / 1000),
                "last_online_ms": last_online_ms,
            },
        }
    )
