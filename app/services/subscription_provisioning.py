from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Node, Plan, Subscription, User
from app.services.xui_client import XUIClient, XUIClientError, _traffic_limit_bytes_from_gb


class SubscriptionProvisioningError(Exception):
    """套餐开通失败（节点不可用、X-UI 调用失败等）。"""


@dataclass
class ProvisionResult:
    subscription: Subscription
    subscription_url: str
    node_id: int
    node_name: str
    node_region: str
    client_uuid: str


def _select_node_for_user(user: User) -> Node | None:
    if user.current_node_id:
        n = Node.query.filter_by(id=user.current_node_id, is_enabled=True).first()
        if n:
            return n
    return Node.query.filter_by(is_enabled=True).order_by(Node.id.asc()).first()


def _compute_stacked_expiry_ms(now: datetime, current_expiry_ms: int, duration_days: int) -> int:
    """在「当前到期」与「现在」中取较晚者为起点，再延长 duration_days（与续费叠加一致）。"""
    if not current_expiry_ms or current_expiry_ms <= 0:
        base = now
    else:
        cur = datetime.fromtimestamp(current_expiry_ms / 1000.0, tz=timezone.utc)
        base = max(now, cur)
    new_end = base + timedelta(days=int(duration_days))
    return int(new_end.timestamp() * 1000)


def _compute_stacked_total_bytes(current_total_bytes: int, plan_gb: float) -> int:
    """
    流量叠加：新上限 = 原面板总限额（字节）+ 本单套餐 GB 对应字节。
    原限额为 0 视为「不限」，首次叠加只设为本单流量。
    """
    extra = _traffic_limit_bytes_from_gb(plan_gb if plan_gb and plan_gb > 0 else None)
    if not current_total_bytes or current_total_bytes <= 0:
        return extra
    return int(current_total_bytes) + extra


def _remaining_gb_from_snapshot(total_bytes: int, up: int, down: int) -> float:
    if total_bytes <= 0:
        return 0.0
    used = max(0, int(up) + int(down))
    rem = max(0, int(total_bytes) - used)
    return round(rem / (1024.0 * 1024.0 * 1024.0), 4)


def provision_plan_for_user(user_id: int, plan_id: int) -> ProvisionResult:
    """
    用户购买套餐：从 X-UI 读取当前限额/到期，叠加本单时长与流量后写回面板；
    同时写入一条 subscriptions 订单记录，并更新 users。
    """
    user = User.query.get(user_id)
    plan = Plan.query.filter_by(id=plan_id, is_enabled=True).first()
    if not user:
        raise SubscriptionProvisioningError("user not found")
    if not plan:
        raise SubscriptionProvisioningError("plan not found")

    node = _select_node_for_user(user)
    if not node:
        raise SubscriptionProvisioningError("no enabled node available")

    now = datetime.now(timezone.utc)
    plan_gb = float(plan.traffic_limit_gb)
    duration_days = int(plan.duration_days)

    xui = XUIClient.from_node(node)

    try:
        if user.uuid:
            snap = xui.get_client_traffic_snapshot(user.email)
            if snap is None:
                raise SubscriptionProvisioningError(
                    "x-ui: cannot read client traffic (check email exists on panel)"
                )
            total_b = _compute_stacked_total_bytes(int(snap.get("total") or 0), plan_gb)
            exp_ms = _compute_stacked_expiry_ms(now, int(snap.get("expiryTime") or 0), duration_days)
            link = xui.update_client_quota_raw(
                client_uuid=user.uuid,
                username=user.username,
                email=user.email,
                total_bytes=total_b,
                expiry_time_ms=exp_ms,
            )
            client_uuid = user.uuid
            rem_gb = _remaining_gb_from_snapshot(total_b, snap.get("up") or 0, snap.get("down") or 0)
        else:
            expires_at = now + timedelta(days=duration_days)
            exp_ms = int(expires_at.timestamp() * 1000)
            client_uuid, link = xui.create_vless_user(
                user.username,
                user.email,
                total_gb=plan_gb,
                expiry_time_ms=exp_ms,
            )
            total_b = _traffic_limit_bytes_from_gb(plan_gb if plan_gb > 0 else None)
            rem_gb = float(plan_gb) if plan_gb > 0 else 0.0
    except XUIClientError as exc:
        raise SubscriptionProvisioningError(str(exc)) from exc

    expires_at = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)

    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        started_at=now,
        expires_at=expires_at,
        traffic_limit_gb=plan_gb,
        traffic_remaining_gb=rem_gb,
    )
    user.uuid = client_uuid
    user.vless_link = link
    user.current_node_id = node.id

    db.session.add(sub)
    db.session.commit()

    return ProvisionResult(
        subscription=sub,
        subscription_url=link,
        node_id=node.id,
        node_name=node.name,
        node_region=node.region,
        client_uuid=client_uuid,
    )
