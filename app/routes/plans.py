import re
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Node, PaymentOrder, Plan, Subscription
from app.services.checkout_catalog import (
    TIER_LABELS,
    TIER_TO_PLAN_NAME,
    PERIOD_LABELS,
    VALID_RECHARGE_PACK_GB,
    expected_amount,
    expected_recharge_pack_amount,
    resolve_traffic_and_duration,
    VALID_PERIODS,
    VALID_TIERS,
)
from app.services.subscription_provisioning import (
    SubscriptionProvisioningError,
    provision_recharge_for_user,
    provision_upgrade_for_user,
)
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required

_ALIPAY_TRADE_NO_RE = re.compile(r"^\d{16,28}$")


def _validate_alipay_trade_no(trade_no: str) -> tuple[bool, str]:
    s = (trade_no or "").strip()
    if not s:
        return False, "请填写支付宝交易号"
    if not _ALIPAY_TRADE_NO_RE.fullmatch(s):
        return False, "支付宝交易号须为 16～28 位纯数字"
    return True, ""


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


def _local_fallback_dict(user) -> dict | None:
    """最近一次订单记录，面板不可用时给用户看参考（与 X-UI 可能不一致）。"""
    s = (
        Subscription.query.filter_by(user_id=user.id)
        .options(joinedload(Subscription.plan))
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if not s:
        return None
    return {
        "expires_at_iso": _aware(s.expires_at).isoformat(),
        "traffic_limit_gb": float(s.traffic_limit_gb),
        "traffic_remaining_gb": float(s.traffic_remaining_gb),
        "plan_name": s.plan.name if s.plan else "",
        "source": "subscription",
    }


def _has_active_plan_local(user) -> bool:
    s = (
        Subscription.query.filter_by(user_id=user.id)
        .options(joinedload(Subscription.plan))
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if not s:
        return False
    now = datetime.now(timezone.utc)
    exp = _aware(s.expires_at)
    not_expired = exp > now
    has_remaining = float(s.traffic_remaining_gb or 0) > 0
    unlimited_cap = float(s.traffic_limit_gb or 0) <= 0
    return bool(not_expired and (has_remaining or unlimited_cap))


@plans_bp.get("")
def list_plans():
    items = Plan.query.filter_by(is_enabled=True).order_by(Plan.id.asc()).all()
    return jsonify({"success": True, "data": {"plans": [_plan_dict(p) for p in items]}})


@plans_bp.get("/xui-status")
@jwt_required
def xui_status():
    """从当前节点对应 3X-UI 面板拉取该邮箱客户端的实时流量与到期（与面板一致）。"""
    user = g.current_user
    try:
        node = _node_for_user(user)
        if not node:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "available": False,
                        "message": "未配置可用节点，请在后台启用至少一个节点。",
                        "local_fallback": _local_fallback_dict(user),
                        "has_active_plan": _has_active_plan_local(user),
                    },
                }
            )

        xui = XUIClient.from_node(node)
        try:
            snap = xui.get_client_traffic_snapshot(user.email, user.uuid)
        except XUIClientError as exc:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "available": False,
                        "message": f"无法连接 3X-UI 面板：{exc}",
                        "local_fallback": _local_fallback_dict(user),
                        "has_active_plan": _has_active_plan_local(user),
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
                        "local_fallback": _local_fallback_dict(user),
                        "has_active_plan": _has_active_plan_local(user),
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

        # 对于新注册但尚未开通套餐的用户，某些面板会返回 total=0 且 up=down=0。
        # 这种场景下，前端不应展示为「不限」，而是清晰地显示为 0。
        looks_like_new_user = total <= 0 and used <= 0

        unlimited_traffic = total <= 0 and not looks_like_new_user
        if unlimited_traffic:
            remaining_bytes = None
            remaining_display = "不限"
        else:
            remaining_bytes = max(0, total - used)
            remaining_display = _format_bytes(remaining_bytes) if remaining_bytes > 0 else "0 B"
        has_active_plan = bool(
            not looks_like_new_user
            and (exp_ms <= 0 or exp_ms > int(datetime.now(timezone.utc).timestamp() * 1000))
            and (unlimited_traffic or (remaining_bytes is not None and remaining_bytes > 0))
        )
        # 面板快照滞后（仍显示 total=0）时，以库内订阅为准，避免控制台一直像「未开通」
        has_active_plan = has_active_plan or _has_active_plan_local(user)

        local_fb = _local_fallback_dict(user)
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
                    "unlimited_traffic": unlimited_traffic,
                    "unlimited_expiry": exp_ms <= 0,
                    "remaining_bytes": remaining_bytes,
                    "remaining_display": remaining_display,
                    "subscription_url": snap.get("subscriptionUrl") or None,
                    "total_display": _format_bytes(total) if total > 0 else "不限",
                    "local_fallback": local_fb,
                    "current_plan_name": (local_fb or {}).get("plan_name") if local_fb else None,
                    "has_active_plan": has_active_plan,
                },
            }
        )
    except Exception as exc:
        current_app.logger.exception("xui-status failed user_id=%s", getattr(user, "id", None))
        return jsonify(
            {
                "success": True,
                "data": {
                    "available": False,
                    "message": f"读取用量失败：{exc}",
                    "local_fallback": _local_fallback_dict(user),
                    "has_active_plan": _has_active_plan_local(user),
                },
            }
        )


@plans_bp.post("/recharge")
@jwt_required
def recharge():
    """
    续费套餐（Recharge）：叠加流量但不改变到期时间。
    JSON: { "traffic_gb": number }
    """
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    raw_gb = payload.get("traffic_gb")
    try:
        traffic_gb = float(raw_gb)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "traffic_gb 必须是数字"}), 400

    try:
        result = provision_recharge_for_user(user.id, traffic_gb)
    except SubscriptionProvisioningError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except XUIClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    return jsonify(
        {
            "success": True,
            "message": "续费成功，流量已更新",
            "data": {
                "subscription_url": result.subscription_url,
                "client_uuid": result.client_uuid,
            },
        }
    )


@plans_bp.post("/checkout-order")
@jwt_required
def checkout_order_create():
    """
    用户提交支付宝交易号后创建待审核订单（不立即开通）。
    JSON: { "tier", "period", "trade_no", "amount" }
    - trade_no: 支付宝交易号，16～28 位纯数字
    - tier: starter | standard | pro
    - period: weekly | monthly | quarterly | half | yearly
    """
    user = g.current_user
    payload = request.get_json(silent=True) or {}

    tier = str(payload.get("tier") or "").strip().lower()
    period_key = str(payload.get("period") or "").strip().lower()
    trade_no = str(payload.get("trade_no") or "").strip()

    if tier not in VALID_TIERS:
        return jsonify({"success": False, "message": "无效的套餐 tier"}), 400
    if period_key not in VALID_PERIODS:
        return jsonify({"success": False, "message": "无效的计费周期 period"}), 400
    ok_trade, trade_msg = _validate_alipay_trade_no(trade_no)
    if not ok_trade:
        return jsonify({"success": False, "message": trade_msg}), 400

    exp = expected_amount(tier, period_key)
    if exp is None:
        return jsonify({"success": False, "message": "价格表无此组合"}), 400

    raw_amt = payload.get("amount")
    try:
        amt_client = Decimal(str(raw_amt))
    except Exception:
        return jsonify({"success": False, "message": "amount 必须是数字"}), 400

    if amt_client != exp:
        return jsonify({"success": False, "message": "金额与服务器价目不一致，请刷新页面"}), 400

    if PaymentOrder.query.filter_by(alipay_trade_no=trade_no).first():
        return jsonify({"success": False, "message": "该支付宝订单号已提交过"}), 409

    plan_name = TIER_TO_PLAN_NAME[tier]
    plan = Plan.query.filter_by(name=plan_name, is_enabled=True).first()
    if not plan:
        return jsonify({"success": False, "message": f"未找到套餐 {plan_name}"}), 400

    try:
        traffic_gb, duration_days = resolve_traffic_and_duration(tier, period_key)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    # 库内唯一键：与支付宝交易号一致，不再使用单独的「系统订单号 ORD…」
    row = PaymentOrder(
        public_order_id=trade_no,
        user_id=user.id,
        user_email=user.email,
        plan_slug=tier,
        period_key=period_key,
        plan_label=TIER_LABELS.get(tier, tier),
        period_label=PERIOD_LABELS.get(period_key, period_key),
        amount=exp,
        alipay_trade_no=trade_no,
        status="waiting",
        traffic_gb=traffic_gb,
        duration_days=duration_days,
        plan_id=plan.id,
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "message": "该订单已提交过或交易号冲突，请勿重复提交"}), 409

    return jsonify(
        {
            "success": True,
            "message": "订单已提交，请等待人工审核开通",
            "data": {
                "db_id": row.id,
                "status": "waiting",
            },
        }
    )


@plans_bp.post("/recharge-checkout-order")
@jwt_required
def recharge_checkout_order_create():
    """
    流量包：提交支付宝交易号 → 待审核；管理员确认后叠加流量（不改变到期）。
    JSON: { "traffic_gb", "trade_no", "amount" }
    """
    user = g.current_user
    payload = request.get_json(silent=True) or {}

    trade_no = str(payload.get("trade_no") or "").strip()
    ok_trade, trade_msg = _validate_alipay_trade_no(trade_no)
    if not ok_trade:
        return jsonify({"success": False, "message": trade_msg}), 400

    raw_gb = payload.get("traffic_gb")
    try:
        gb_int = int(float(raw_gb))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "traffic_gb 无效"}), 400

    if gb_int not in VALID_RECHARGE_PACK_GB:
        return jsonify({"success": False, "message": "无效的流量包规格"}), 400
    try:
        if float(raw_gb) != float(gb_int):
            return jsonify({"success": False, "message": "无效的流量包规格"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "无效的流量包规格"}), 400

    exp = expected_recharge_pack_amount(gb_int)
    if exp is None:
        return jsonify({"success": False, "message": "价格表无此流量包"}), 400

    raw_amt = payload.get("amount")
    try:
        amt_client = Decimal(str(raw_amt))
    except Exception:
        return jsonify({"success": False, "message": "amount 必须是数字"}), 400

    if amt_client != exp:
        return jsonify({"success": False, "message": "金额与服务器价目不一致，请刷新页面"}), 400

    if PaymentOrder.query.filter_by(alipay_trade_no=trade_no).first():
        return jsonify({"success": False, "message": "该支付宝订单号已提交过"}), 409

    plan = Plan.query.filter_by(is_enabled=True).order_by(Plan.id.asc()).first()
    if not plan:
        return jsonify({"success": False, "message": "未找到可用套餐记录，请联系管理员"}), 503

    row = PaymentOrder(
        public_order_id=trade_no,
        user_id=user.id,
        user_email=user.email,
        plan_slug="recharge",
        period_key="pack",
        plan_label=f"流量包 +{gb_int}GB",
        period_label="一次性叠加",
        amount=exp,
        alipay_trade_no=trade_no,
        status="waiting",
        traffic_gb=float(gb_int),
        duration_days=0,
        plan_id=plan.id,
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "message": "该订单已提交过或交易号冲突，请勿重复提交"}), 409

    return jsonify(
        {
            "success": True,
            "message": "订单已提交，请等待人工审核后叠加流量",
            "data": {"db_id": row.id, "status": "waiting"},
        }
    )


@plans_bp.post("/upgrade")
@jwt_required
def upgrade():
    """
    升级套餐（Upgrade）：覆盖当前套餐、重置流量并更新到期时间。
    JSON: { "plan_id": int }
    """
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    raw_pid = payload.get("plan_id")
    try:
        plan_id = int(raw_pid)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "plan_id 必须是整数"}), 400

    try:
        result = provision_upgrade_for_user(user.id, plan_id)
    except SubscriptionProvisioningError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except XUIClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    return jsonify(
        {
            "success": True,
            "message": "套餐更新成功，流量与到期时间已同步",
            "data": {
                "subscription_url": result.subscription_url,
                "client_uuid": result.client_uuid,
            },
        }
    )
