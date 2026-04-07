"""管理员 API：支付订单确认后调用 X-UI 开通。用户流量、到期、IP 限制等请在 3X-UI 面板管理。"""

from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import PaymentOrder
from app.services.subscription_provisioning import (
    SubscriptionProvisioningError,
    provision_order_quota,
    provision_recharge_for_user,
)

admin_bp = Blueprint("admin_api", __name__)


def admin_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        expected = (current_app.config.get("ADMIN_TOKEN") or "").strip()
        if not expected:
            return jsonify(
                {
                    "success": False,
                    "message": "服务器未配置 ADMIN_TOKEN（请在项目根目录 .env 中设置并重启进程，勿仅修改 .env.example）",
                }
            ), 403
        got = request.headers.get("X-Admin-Token", "").strip()
        if got != expected:
            return jsonify({"success": False, "message": "admin unauthorized"}), 401
        return handler(*args, **kwargs)

    return wrapper


def _order_to_dict(r: PaymentOrder) -> dict:
    return {
        "id": r.id,
        "user_email": r.user_email,
        "plan": r.plan_label,
        "period": r.period_label,
        "amount": float(r.amount),
        "alipay_trade_no": r.alipay_trade_no,
        "status": r.status,
        "client_uuid": r.client_uuid,
        "subscription_url": r.subscription_url,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@admin_bp.get("/orders")
@admin_required
def list_payment_orders():
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 10, type=int) or 10
    page = max(1, page)
    per_page = max(1, min(per_page, 100))

    total = PaymentOrder.query.count()
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages

    rows = (
        PaymentOrder.query.order_by(PaymentOrder.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    waiting_n = PaymentOrder.query.filter_by(status="waiting").count()
    completed_n = PaymentOrder.query.filter_by(status="completed").count()

    return jsonify(
        {
            "success": True,
            "data": {
                "orders": [_order_to_dict(r) for r in rows],
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "stats": {"waiting": waiting_n, "completed": completed_n},
            },
        }
    )


def _delete_order_row(order_id: int):
    row = PaymentOrder.query.get(order_id)
    if not row:
        return jsonify({"success": False, "message": "order not found"}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"success": True, "message": "订单已删除"})


@admin_bp.delete("/orders/<int:order_id>")
@admin_required
def delete_payment_order(order_id: int):
    """部分 Nginx 默认不转发 DELETE，会 404；前端优先用 POST …/delete。"""
    return _delete_order_row(order_id)


@admin_bp.post("/orders/<int:order_id>/delete")
@admin_required
def delete_payment_order_post(order_id: int):
    return _delete_order_row(order_id)


@admin_bp.post("/orders/<int:order_id>/confirm")
@admin_required
def confirm_payment_order(order_id: int):
    row = PaymentOrder.query.get(order_id)
    if not row:
        return jsonify({"success": False, "message": "order not found"}), 404
    if row.status != "waiting":
        return jsonify({"success": False, "message": "订单已处理或非 waiting 状态"}), 400

    try:
        if row.plan_slug == "recharge" and row.period_key == "pack":
            result = provision_recharge_for_user(row.user_id, float(row.traffic_gb))
        else:
            result = provision_order_quota(
                row.user_id,
                row.plan_id,
                float(row.traffic_gb),
                int(row.duration_days),
            )
    except SubscriptionProvisioningError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    fresh = PaymentOrder.query.get(order_id)
    if not fresh:
        return jsonify({"success": False, "message": "order missing after provision"}), 500
    fresh.status = "completed"
    fresh.client_uuid = result.client_uuid
    fresh.subscription_url = result.subscription_url
    fresh.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    ok_msg = (
        "已叠加流量并同步 X-UI"
        if row.plan_slug == "recharge" and row.period_key == "pack"
        else "已开通并同步 X-UI"
    )
    return jsonify(
        {
            "success": True,
            "message": ok_msg,
            "data": {
                "client_uuid": result.client_uuid,
                "subscription_url": result.subscription_url,
            },
        }
    )
