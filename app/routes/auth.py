from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import bcrypt, db
from app.models import Node, Subscription, User, UserNodeAccess
from app.services.auth_service import generate_access_token
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required

auth_bp = Blueprint("auth", __name__)


def _has_active_plan(user: User) -> bool:
    """后端判定是否有有效套餐（用于前端页面显隐控制）。"""
    latest = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if not latest:
        return False
    now = datetime.now(timezone.utc)
    exp = latest.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    not_expired = exp > now
    # 剩余流量>0 视为有效；若未来支持不限流量可在此扩展条件
    has_remaining = float(latest.traffic_remaining_gb or 0) > 0
    return bool(not_expired and has_remaining)


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
    try:
        data = request.get_json(silent=True) or {}
        identity = (data.get("identity") or "").strip()
        password = data.get("password") or ""
        if not identity or not password:
            return jsonify({"success": False, "message": "请输入用户名/邮箱与密码"}), 400

        user = User.query.filter(
            (User.username == identity) | (User.email == identity.lower())
        ).first()
        if not user:
            return jsonify({"success": False, "message": "用户名或密码错误"}), 401

        if not bcrypt.check_password_hash(user.password_hash, password):
            return jsonify({"success": False, "message": "用户名或密码错误"}), 401

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
    except SQLAlchemyError as exc:
        current_app.logger.exception("login database error")
        return jsonify({"success": False, "message": f"数据库错误：{exc}"}), 500
    except Exception as exc:
        current_app.logger.exception("login failed")
        return jsonify({"success": False, "message": str(exc)}), 500


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
                }
            },
        }
    )
