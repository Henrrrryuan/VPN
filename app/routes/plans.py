from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from app.models import Node, Plan, Subscription
from app.services.subscription_provisioning import SubscriptionProvisioningError, provision_plan_for_user
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required


def _node_for_user(user) -> Node | None:
    if user.current_node_id:
        n = Node.query.filter_by(id=user.current_node_id, is_enabled=True).first()
        if n:
            return n
    return Node.query.filter_by(is_enabled=True).order_by(Node.id.asc()).first()


def _format_bytes(n: int) -> str:
    n = max(0, int(n))
    if n < 1024:
        return f"{n} B"
    val = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        val /= 1024.0
        if val < 1024.0 or unit == "TB":
            return f"{val:.2f} {unit}"
    return f"{n} B"

plans_bp = Blueprint("plans", __name__)


def _plan_dict(p: Plan) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "price": float(p.price),
        "traffic_limit_gb": p.traffic_limit_gb,
        "duration_days": p.duration_days,
    }


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _subscription_dict(s: Subscription) -> dict:
    now = datetime.now(timezone.utc)
    exp = _aware(s.expires_at)
    active = exp > now
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "plan_name": s.plan.name if s.plan else "",
        "started_at": _aware(s.started_at).isoformat(),
        "expires_at": _aware(s.expires_at).isoformat(),
        "traffic_limit_gb": s.traffic_limit_gb,
        "traffic_remaining_gb": s.traffic_remaining_gb,
        "is_active": active,
    }


@plans_bp.get("")
def list_plans():
    items = Plan.query.filter_by(is_enabled=True).order_by(Plan.id.asc()).all()
    return jsonify({"success": True, "data": {"plans": [_plan_dict(p) for p in items]}})


@plans_bp.get("/xui-status")
@jwt_required
def xui_status():
    """从当前节点对应 3X-UI 面板拉取该邮箱客户端的实时流量与到期（与面板一致）。"""
    user = g.current_user
    node = _node_for_user(user)
    if not node:
        return jsonify(
            {
                "success": True,
                "data": {
                    "available": False,
                    "message": "未配置可用节点，请在后台启用至少一个节点。",
                },
            }
        )

    xui = XUIClient.from_node(node)
    try:
        snap = xui.get_client_traffic_snapshot(user.email, user.uuid)
    except XUIClientError as exc:
        # 返回 200 + available:false，避免前端把面板连接/鉴权失败当成「无法拉取」且看不到原因
        return jsonify(
            {
                "success": True,
                "data": {
                    "available": False,
                    "message": f"无法连接 3X-UI 面板：{exc}",
                },
            }
        )

    if not snap:
        return jsonify(
            {
                "success": True,
                "data": {
                    "available": False,
                    "message": "面板中暂无该邮箱的流量记录（请确认已注册且节点对应同一面板）",
                },
            }
        )

    total = int(snap.get("total") or 0)
    up = int(snap.get("up") or 0)
    down = int(snap.get("down") or 0)
    used = up + down
    all_time = int(snap.get("allTime") or 0)
    exp_ms = int(snap.get("expiryTime") or 0)
    exp_iso = None
    if exp_ms > 0:
        exp_iso = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc).isoformat()

    return jsonify(
        {
            "success": True,
            "data": {
                "available": True,
                "email": user.email,
                "total_bytes": total,
                "used_bytes": used,
                "up_bytes": up,
                "down_bytes": down,
                "all_time_bytes": all_time,
                "expiry_time_ms": exp_ms,
                "expiry_iso": exp_iso,
                "unlimited_traffic": total <= 0,
                "unlimited_expiry": exp_ms <= 0,
                "subscription_url": snap.get("subscriptionUrl") or None,
                "total_display": _format_bytes(total) if total > 0 else "不限",
                "used_display": _format_bytes(used),
                "all_time_display": _format_bytes(all_time),
            },
        }
    )


@plans_bp.get("/subscriptions")
@jwt_required
def list_my_subscriptions():
    user = g.current_user
    rows = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .all()
    )
    return jsonify({"success": True, "data": {"subscriptions": [_subscription_dict(s) for s in rows]}})


@plans_bp.post("/purchase")
@jwt_required
def purchase():
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    raw_pid = payload.get("plan_id")
    try:
        plan_id = int(raw_pid)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "plan_id must be an integer"}), 400

    try:
        result = provision_plan_for_user(user.id, plan_id)
    except SubscriptionProvisioningError as exc:
        msg = str(exc)
        if "plan not found" in msg.lower() or "user not found" in msg.lower():
            return jsonify({"success": False, "message": msg}), 404
        return jsonify({"success": False, "message": msg}), 502

    return (
        jsonify(
            {
                "success": True,
                "message": "purchase recorded; x-ui limits stacked",
                "data": {
                    "subscription": _subscription_dict(result.subscription),
                    "subscription_url": result.subscription_url,
                    "node": {
                        "id": result.node_id,
                        "name": result.node_name,
                        "region": result.node_region,
                    },
                    "client_uuid": result.client_uuid,
                },
            }
        ),
        201,
    )
