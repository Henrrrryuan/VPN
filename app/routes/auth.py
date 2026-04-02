from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g, current_app

from app.extensions import bcrypt, db
from app.models import Node, OnlineIpEvent, User, UserNodeAccess
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

    # 统计最近 N 秒内出现过的不同来源 IP 数（精确到 distinct IP）。
    window_sec = int(current_app.config.get("ONLINE_STATS_WINDOW_SEC", 180))
    cutoff = datetime.now(timezone.utc).timestamp() - window_sec
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)

    # 优先使用 access log 上报的数据。为减少偶发残留包误判，要求同一 IP 在窗口内事件数达到门槛。
    min_events_per_ip = int(current_app.config.get("ONLINE_MIN_EVENTS_PER_IP", 3))
    ip_rows = (
        db.session.query(OnlineIpEvent.src_ip, db.func.count(OnlineIpEvent.id).label("event_count"))
        .filter(
            OnlineIpEvent.user_id == user.id,
            OnlineIpEvent.observed_at >= cutoff_dt,
        )
        .group_by(OnlineIpEvent.src_ip)
        .having(db.func.count(OnlineIpEvent.id) >= min_events_per_ip)
        .all()
    )
    online_ip_count = len(ip_rows)

    # 若短时间内曾有上报，则窗口内为 0 也保持真实值 0，不立刻回退到估算。
    grace_sec = int(current_app.config.get("ONLINE_FALLBACK_GRACE_SEC", 120))
    fallback_cutoff = datetime.now(timezone.utc).timestamp() - grace_sec
    fallback_cutoff_dt = datetime.fromtimestamp(fallback_cutoff, tz=timezone.utc)
    has_recent_ingest = (
        db.session.query(OnlineIpEvent.id)
        .filter(
            OnlineIpEvent.user_id == user.id,
            OnlineIpEvent.observed_at >= fallback_cutoff_dt,
        )
        .first()
        is not None
    )

    # 仅在明确开启回退时，且长时间没有上报，才退回到 x-ui lastOnline 估算（最多 1/2）
    fallback_used = False
    last_online_ms = 0
    enable_fallback = bool(current_app.config.get("ONLINE_ENABLE_XUI_FALLBACK", False))
    if enable_fallback and online_ip_count == 0 and not has_recent_ingest:
        xui = XUIClient.from_node(node)
        try:
            traffics = xui.get_client_traffics(user.email)
            last_online_ms = traffics.get("lastOnline") or 0
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            window_ms = int(current_app.config.get("USAGE_ONLINE_WINDOW_MS", "120000"))
            fallback_used = True
            if last_online_ms:
                online_ip_count = 1 if (now_ms - int(last_online_ms)) <= window_ms else 0
        except XUIClientError:
            fallback_used = True

    return jsonify(
        {
            "success": True,
            "data": {
                "limit_ip": limit_ip,
                "online_ip_count": online_ip_count,
                "online_window_sec": window_sec,
                "fallback_used": fallback_used,
                "last_online_ms": last_online_ms,
            },
        }
    )
