from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from app.extensions import db
from app.models import Plan, Subscription
from app.utils.auth_guard import jwt_required

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
    active = exp > now and s.traffic_remaining_gb > 0
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
    plan_id = payload.get("plan_id")
    if plan_id is None:
        return jsonify({"success": False, "message": "plan_id is required"}), 400

    plan = Plan.query.filter_by(id=plan_id, is_enabled=True).first()
    if not plan:
        return jsonify({"success": False, "message": "plan not found"}), 404

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=int(plan.duration_days))
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        started_at=now,
        expires_at=expires,
        traffic_limit_gb=float(plan.traffic_limit_gb),
        traffic_remaining_gb=float(plan.traffic_limit_gb),
    )
    db.session.add(sub)
    db.session.commit()

    return (
        jsonify(
            {
                "success": True,
                "message": "purchase recorded",
                "data": {"subscription": _subscription_dict(sub)},
            }
        ),
        201,
    )
