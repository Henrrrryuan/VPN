"""管理员 API：在 SaaS 侧调整用户到期时间与流量上限，并同步到 3X-UI 面板。"""

from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Subscription, User
from app.routes.plans import _node_for_user, _subscription_dict
from app.services.subscription_provisioning import _remaining_gb_from_snapshot
from app.services.xui_client import XUIClient, XUIClientError, _traffic_limit_bytes_from_gb

admin_bp = Blueprint("admin_api", __name__)


def admin_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        expected = (current_app.config.get("ADMIN_TOKEN") or "").strip()
        if not expected:
            return jsonify({"success": False, "message": "admin disabled (set ADMIN_TOKEN)"}), 404
        got = request.headers.get("X-Admin-Token", "").strip()
        if got != expected:
            return jsonify({"success": False, "message": "admin unauthorized"}), 401
        return handler(*args, **kwargs)

    return wrapper


@admin_bp.get("/users")
@admin_required
def list_users():
    rows = User.query.order_by(User.id.asc()).all()
    return jsonify(
        {
            "success": True,
            "data": {
                "users": [
                    {
                        "id": u.id,
                        "username": u.username,
                        "email": u.email,
                        "uuid": u.uuid,
                        "current_node_id": u.current_node_id,
                    }
                    for u in rows
                ]
            },
        }
    )


@admin_bp.post("/users/<int:user_id>/limits")
@admin_required
def set_user_limits(user_id: int):
    """
    将用户到期时间与总流量上限写入 3X-UI，并尽量同步最近一条 subscriptions 记录。
    JSON: { "expiry_time_ms": int, "total_gb": number }
    - expiry_time_ms: Unix 毫秒，0 表示不限到期
    - total_gb: 总限额（GB），0 或省略表示不限流量（与面板 total=0 一致）
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "user not found"}), 404

    payload = request.get_json(silent=True) or {}
    if "expiry_time_ms" not in payload:
        return jsonify({"success": False, "message": "expiry_time_ms is required"}), 400

    try:
        exp_ms = int(payload["expiry_time_ms"])
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "expiry_time_ms must be an integer"}), 400

    raw_gb = payload.get("total_gb")
    if raw_gb is None:
        total_gb = 0.0
    else:
        try:
            total_gb = float(raw_gb)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "total_gb must be a number"}), 400

    node = _node_for_user(user)
    if not node:
        return jsonify({"success": False, "message": "no enabled node"}), 502

    total_bytes = _traffic_limit_bytes_from_gb(total_gb if total_gb and total_gb > 0 else None)

    xui = XUIClient.from_node(node)
    try:
        link = xui.update_client_quota_raw(
            client_uuid=user.uuid,
            username=user.username,
            email=user.email,
            total_bytes=total_bytes,
            expiry_time_ms=exp_ms,
        )
        snap = xui.get_client_traffic_snapshot(user.email, user.uuid)
    except XUIClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    user.vless_link = link or user.vless_link

    sub = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if sub and snap:
        if exp_ms > 0:
            sub.expires_at = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)
        if total_gb and total_gb > 0:
            sub.traffic_limit_gb = total_gb
        sub.traffic_remaining_gb = _remaining_gb_from_snapshot(
            int(snap.get("total") or 0),
            int(snap.get("up") or 0),
            int(snap.get("down") or 0),
        )

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "limits synced to x-ui",
            "data": {
                "user_id": user.id,
                "subscription_url": link,
                "subscription": _subscription_dict(sub) if sub else None,
            },
        }
    )
