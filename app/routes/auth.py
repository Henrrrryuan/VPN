from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import nulls_last
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import bcrypt, db
from app.models import Node, PaymentOrder, Subscription, User, UserNodeAccess
from app.services.auth_service import generate_access_token
from app.services.login_rate_limit import is_login_rate_limited
from app.services.checkout_catalog import (
    VALID_PERIODS,
    format_traffic_quota_display,
    infer_period_key_for_traffic,
    PERIOD_LABELS,
    PLAN_NAME_TO_TIER,
)
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required

auth_bp = Blueprint("auth", __name__)

# 固定 bcrypt 串，仅用于「用户不存在」分支对齐校验耗时（明文无关）
_LOGIN_TIMING_DUMMY_HASH = (
    "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIY5p7g7Vy"
)

# 库内 Plan.name（Basic/Pro/Premium）→ 结账页展示名（Starter/Standard/Pro）
_PLAN_DB_TO_DISPLAY = {"Basic": "Starter", "Pro": "Standard", "Premium": "Pro"}


def _latest_subscription(user: User) -> Subscription | None:
    return (
        Subscription.query.filter_by(user_id=user.id)
        .options(joinedload(Subscription.plan))
        .order_by(Subscription.started_at.desc())
        .first()
    )


def _latest_completed_payment_order(user: User) -> PaymentOrder | None:
    return (
        PaymentOrder.query.filter_by(user_id=user.id, status="completed")
        .order_by(nulls_last(PaymentOrder.completed_at.desc()), PaymentOrder.id.desc())
        .first()
    )


def _current_plan_payload(user: User) -> dict | None:
    """
    当前套餐展示：短名 + 周期 + 本周期流量额度。
    例：Pro · 周付用户(47GB/周)
    """
    latest = _latest_subscription(user)
    po = _latest_completed_payment_order(user)
    if not latest and not po:
        return None

    display_label: str | None = None
    plan_db_name: str | None = None
    period_key: str | None = None
    period_label_cn: str | None = None
    traffic_gb_val: float | None = None

    if latest and latest.plan:
        plan_db_name = latest.plan.name
        display_label = _PLAN_DB_TO_DISPLAY.get(plan_db_name, plan_db_name)

    if po:
        if (po.plan_label or "").strip():
            display_label = po.plan_label.strip()
        if po.plan:
            plan_db_name = po.plan.name
        period_key = (po.period_key or "").strip().lower() or None
        if period_key and period_key in VALID_PERIODS:
            period_label_cn = (po.period_label or "").strip() or PERIOD_LABELS.get(period_key, period_key)
            traffic_gb_val = float(po.traffic_gb)
        else:
            period_key = None

    if latest and latest.plan and (period_key is None or traffic_gb_val is None):
        tier = PLAN_NAME_TO_TIER.get(latest.plan.name)
        if tier:
            if traffic_gb_val is None:
                traffic_gb_val = float(latest.traffic_limit_gb)
            if period_key is None:
                inferred = infer_period_key_for_traffic(tier, float(latest.traffic_limit_gb))
                if inferred:
                    period_key = inferred
                    period_label_cn = PERIOD_LABELS.get(period_key, period_key)

    if not display_label:
        return None

    exp_iso: str | None = None
    if latest and latest.expires_at:
        exp = latest.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        exp_iso = exp.isoformat()
    elif po and po.completed_at:
        exp_iso = po.completed_at.isoformat()

    summary = display_label
    if period_label_cn and period_key and period_key in VALID_PERIODS and traffic_gb_val is not None:
        quota_disp = format_traffic_quota_display(period_key, traffic_gb_val)
        summary = f"{display_label} · {period_label_cn}用户({quota_disp})"

    return {
        "label": display_label,
        "summary": summary,
        "plan_db_name": plan_db_name,
        "period_key": period_key,
        "period_label": period_label_cn,
        "traffic_quota_gb": traffic_gb_val,
        "expires_at": exp_iso,
    }


def _has_active_plan(user: User) -> bool:
    """后端判定是否有有效套餐（用于前端页面显隐控制）。"""
    latest = _latest_subscription(user)
    if not latest:
        return False
    now = datetime.now(timezone.utc)
    exp = latest.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    not_expired = exp > now
    has_remaining = float(latest.traffic_remaining_gb or 0) > 0
    unlimited_cap = float(latest.traffic_limit_gb or 0) <= 0
    return bool(not_expired and (has_remaining or unlimited_cap))


@auth_bp.get("/selftest")
def auth_selftest():
    """
    部署排查：不校验 JWT。浏览器或 curl 访问
    GET /api/auth/selftest
    若返回 JSON 且 build 字段存在，说明请求已到本应用 auth 蓝图。
    """
    try:
        n = User.query.count()
        h = bcrypt.generate_password_hash("p").decode("utf-8")
        bcrypt_ok = bcrypt.check_password_hash(h, "p")
        u = User.query.first()
        jwt_ok = False
        if u:
            generate_access_token(u.id)
            jwt_ok = True
        return jsonify(
            {
                "success": True,
                "build": "2026-04-03-auth-selftest",
                "users_count": n,
                "bcrypt": "ok" if bcrypt_ok else "fail",
                "jwt": "ok" if jwt_ok else "skip_no_users",
            }
        )
    except Exception as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "build": "2026-04-03-auth-selftest",
                    "message": str(exc),
                }
            ),
            500,
        )


def _validate_register_payload(data: dict) -> tuple[bool, str]:
    required = ["username", "email", "password"]
    for key in required:
        if not data.get(key):
            return False, f"缺少字段：{key}"
    if len(data["password"]) < 6:
        return False, "密码至少 6 位"
    em = str(data.get("email", "")).strip().lower()
    if "@" not in em or not em.split("@", 1)[1]:
        return False, "请输入有效邮箱（需包含 @）"
    return True, ""


@auth_bp.post("/register")
def register():
    try:
        data = request.get_json(silent=True) or {}
        ok, msg = _validate_register_payload(data)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400

        username = data["username"].strip()
        email = data["email"].strip().lower()
        password = data["password"]

        if User.query.filter_by(username=username).first():
            return jsonify({"success": False, "message": "用户名已被占用"}), 409
        if User.query.filter_by(email=email).first():
            return jsonify({"success": False, "message": "邮箱已被注册"}), 409

        node = Node.query.filter_by(is_enabled=True).order_by(Node.id.asc()).first()
        if not node:
            return jsonify({"success": False, "message": "暂无可用节点，请稍后再试"}), 503

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
                    "message": "注册成功",
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
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.exception("register integrity error")
        return jsonify({"success": False, "message": "数据冲突（用户名或邮箱可能已存在）"}), 409
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.exception("register database error")
        return jsonify({"success": False, "message": f"数据库错误：{exc}"}), 500
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("register failed")
        return jsonify({"success": False, "message": str(exc)}), 500


@auth_bp.post("/login")
def login():
    def _fail(http_code: int, code: str, message: str):
        return jsonify({"success": False, "code": code, "message": message}), http_code

    try:
        if is_login_rate_limited(request.remote_addr or ""):
            return _fail(429, "LOGIN_RATE_LIMITED", "请求过于频繁，请稍后再试")

        data = request.get_json(silent=True) or {}
        identity = (data.get("identity") or "").strip()
        password = data.get("password") or ""
        if not identity or not password:
            return _fail(400, "LOGIN_MISSING_FIELDS", "请输入用户名/邮箱与密码")

        user = User.query.filter(
            (User.username == identity) | (User.email == identity.lower())
        ).first()
        if not user:
            bcrypt.check_password_hash(_LOGIN_TIMING_DUMMY_HASH, password)
            return _fail(401, "LOGIN_INVALID_CREDENTIALS", "用户名或密码错误")

        if not bcrypt.check_password_hash(user.password_hash, password):
            return _fail(401, "LOGIN_INVALID_CREDENTIALS", "用户名或密码错误")

        if bool(getattr(user, "is_disabled", False)):
            return _fail(403, "ACCOUNT_DISABLED", "账号已停用，请联系管理员")

        token = generate_access_token(user.id)
        return jsonify(
            {
                "success": True,
                "message": "登录成功",
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
    except SQLAlchemyError:
        current_app.logger.exception("login database error")
        return _fail(500, "SERVER_ERROR", "服务暂时不可用，请稍后再试")
    except Exception:
        current_app.logger.exception("login failed")
        return _fail(500, "SERVER_ERROR", "服务暂时不可用，请稍后再试")


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
                    "has_active_plan": _has_active_plan(user),
                    "current_plan": _current_plan_payload(user),
                }
            },
        }
    )
