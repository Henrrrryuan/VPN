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


def _coalesce_remaining_with_order_gb(computed_gb: float, order_total_gb: float) -> float:
    """
    面板刚写入后 getClientTraffics 可能仍返回 total=0，快照算出的剩余为 0。
    会导致 subscriptions.traffic_remaining_gb=0 → has_active_plan 为 False、控制台仍像「未开通」。
    若本单明确有套餐流量（GB>0），剩余流量至少不应低于本单额度（直至下次快照正确）。
    """
    floor = float(order_total_gb or 0)
    if floor <= 0:
        return round(float(computed_gb or 0), 4)
    cg = float(computed_gb or 0)
    if cg <= 0:
        return round(floor, 4)
    return round(cg, 4)


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
            rem_gb = _coalesce_remaining_with_order_gb(rem_gb, plan_gb)
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


def _ms_to_datetime_or_far_future(exp_ms: int, now: datetime) -> datetime:
    """
    3X-UI 的 expiryTime：
    - >0：Unix 毫秒时间戳
    - <=0：表示不限到期

    Subscription.expires_at 是非空字段，因此用“很久以后”来近似表示不限到期。
    """
    if exp_ms and exp_ms > 0:
        return datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)
    # 约 100 年，用于表示不限到期（不影响 UI 中无限判定：仍以 X-UI total/expiryTime 为准）
    return now + timedelta(days=36500)


def _gib_from_bytes(total_bytes: int) -> float:
    if total_bytes is None or total_bytes <= 0:
        return 0.0
    return round(float(total_bytes) / (1024.0 * 1024.0 * 1024.0), 4)


def provision_recharge_for_user(user_id: int, traffic_gb: float) -> ProvisionResult:
    """
    续费/流量加购（Recharge）：
    - 叠加到当前剩余流量等价于：在原有 total 上增加 bytes
    - 不改变 expiryTime（到期时间）
    """
    user = User.query.get(user_id)
    if not user:
        raise SubscriptionProvisioningError("user not found")

    if traffic_gb is None or float(traffic_gb) <= 0:
        raise SubscriptionProvisioningError("traffic_gb must be positive")

    node = _select_node_for_user(user)
    if not node:
        raise SubscriptionProvisioningError("no enabled node available")

    now = datetime.now(timezone.utc)
    xui = XUIClient.from_node(node)

    try:
        snap = xui.get_client_traffic_snapshot(user.email, user.uuid)
        if snap is None:
            raise SubscriptionProvisioningError(
                "x-ui: cannot read client traffic (check email exists on panel)"
            )

        resolved_client_uuid = snap.get("client_uuid") or user.uuid
        if not resolved_client_uuid:
            raise SubscriptionProvisioningError(
                "x-ui: cannot resolve client uuid for updateClient (please ensure the client exists on panel)"
            )

        cur_total_bytes = int(snap.get("total") or 0)
        cur_used_bytes = int(snap.get("up") or 0) + int(snap.get("down") or 0)
        cur_expiry_ms = int(snap.get("expiryTime") or 0)
        extra_bytes = _traffic_limit_bytes_from_gb(float(traffic_gb))

        # total=0 在 X-UI 里可能有两种含义：
        # - 确实“无限流量”（通常会伴随 up/down > 0）
        # - 新账号尚未开通套餐（常见表现：total=0 且 up/down=0）
        # 对“新账号未开通”这种场景，充值应当初始化 total 为 extra_bytes，
        # 否则面板会保持 total=0（看起来充值没生效）。
        if cur_total_bytes and cur_total_bytes > 0:
            new_total_bytes = int(cur_total_bytes) + int(extra_bytes)
        else:
            new_total_bytes = 0 if cur_used_bytes > 0 else int(extra_bytes)

        link = xui.update_client_quota_raw(
            client_uuid=resolved_client_uuid,
            username=user.username,
            email=user.email,
            total_bytes=new_total_bytes,
            expiry_time_ms=cur_expiry_ms,
        )

        snap2 = xui.get_client_traffic_snapshot(user.email, resolved_client_uuid)
        if snap2 is None:
            raise SubscriptionProvisioningError("x-ui: cannot read client traffic after recharge")

        remaining_gb = _remaining_gb_from_snapshot(
            int(snap2.get("total") or 0),
            int(snap2.get("up") or 0),
            int(snap2.get("down") or 0),
        )
        remaining_gb = _coalesce_remaining_with_order_gb(remaining_gb, float(traffic_gb))
        expires_at = _ms_to_datetime_or_far_future(int(snap2.get("expiryTime") or 0), now)

    except XUIClientError as exc:
        raise SubscriptionProvisioningError(str(exc)) from exc

    # 更新最近一次订阅记录（用于本地兜底展示；前端已不展示购买记录列表）
    latest_sub = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if latest_sub:
        latest_sub.started_at = now
        # 充值不改变到期：expires_at 与面板相同（或不限到期的近似值）
        latest_sub.expires_at = expires_at
        latest_sub.traffic_limit_gb = _gib_from_bytes(int(snap2.get("total") or 0))
        latest_sub.traffic_remaining_gb = remaining_gb
        sub = latest_sub
    else:
        # 没有订阅记录时，沿用 Basic 作为占位 plan_id（不影响 X-UI 的 expiry/total）
        base_plan = Plan.query.filter_by(is_enabled=True).order_by(Plan.id.asc()).first()
        plan_id = base_plan.id if base_plan else 1
        sub = Subscription(
            user_id=user.id,
            plan_id=plan_id,
            started_at=now,
            expires_at=expires_at,
            traffic_limit_gb=_gib_from_bytes(new_total_bytes),
            traffic_remaining_gb=remaining_gb,
        )
        db.session.add(sub)

    user.uuid = resolved_client_uuid
    user.vless_link = link
    user.current_node_id = node.id
    db.session.commit()

    return ProvisionResult(
        subscription=sub,
        subscription_url=link,
        node_id=node.id,
        node_name=node.name,
        node_region=node.region,
        client_uuid=resolved_client_uuid,
    )


def provision_upgrade_for_user(user_id: int, plan_id: int) -> ProvisionResult:
    """
    套餐升级（Upgrade）：
    - 覆盖当前套餐
    - 重置流量上限
    - 更新到期时间 = now + duration_days
    """
    user = User.query.get(user_id)
    if not user:
        raise SubscriptionProvisioningError("user not found")

    plan = Plan.query.filter_by(id=plan_id, is_enabled=True).first()
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
        exp_ms = int((now + timedelta(days=duration_days)).timestamp() * 1000)
        total_bytes = _traffic_limit_bytes_from_gb(plan_gb if plan_gb and plan_gb > 0 else None)

        # 尽量从现有面板记录解析 client_uuid；避免 user.uuid 为空时误创建重复客户端。
        snap_first = xui.get_client_traffic_snapshot(user.email, user.uuid)
        resolved_client_uuid = None
        if user.uuid:
            resolved_client_uuid = user.uuid
        elif snap_first:
            resolved_client_uuid = snap_first.get("client_uuid")

        if resolved_client_uuid:
            link = xui.update_client_quota_raw(
                client_uuid=resolved_client_uuid,
                username=user.username,
                email=user.email,
                total_bytes=total_bytes,
                expiry_time_ms=exp_ms,
            )
            client_uuid = resolved_client_uuid
        else:
            client_uuid, link = xui.create_vless_user(
                user.username,
                user.email,
                total_gb=plan_gb,
                expiry_time_ms=exp_ms,
            )

        snap2 = xui.get_client_traffic_snapshot(user.email, client_uuid)
        if snap2 is None:
            raise SubscriptionProvisioningError("x-ui: cannot read client traffic after upgrade")

        remaining_gb = _remaining_gb_from_snapshot(
            int(snap2.get("total") or 0),
            int(snap2.get("up") or 0),
            int(snap2.get("down") or 0),
        )
        remaining_gb = _coalesce_remaining_with_order_gb(remaining_gb, plan_gb)
        expires_at = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)

    except XUIClientError as exc:
        raise SubscriptionProvisioningError(str(exc)) from exc

    latest_sub = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if latest_sub:
        latest_sub.started_at = now
        latest_sub.plan_id = plan.id
        latest_sub.expires_at = expires_at
        latest_sub.traffic_limit_gb = plan_gb
        latest_sub.traffic_remaining_gb = remaining_gb
        sub = latest_sub
    else:
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            started_at=now,
            expires_at=expires_at,
            traffic_limit_gb=plan_gb,
            traffic_remaining_gb=remaining_gb,
        )
        db.session.add(sub)

    user.uuid = client_uuid
    user.vless_link = link
    user.current_node_id = node.id
    db.session.commit()

    return ProvisionResult(
        subscription=sub,
        subscription_url=link,
        node_id=node.id,
        node_name=node.name,
        node_region=node.region,
        client_uuid=client_uuid,
    )


def provision_order_quota(user_id: int, plan_id: int, traffic_gb: float, duration_days: int) -> ProvisionResult:
    """
    按订单维度写入 X-UI：使用显式流量（GB）与时长（天），逻辑与套餐升级一致。
    用于管理员确认收款后开通/覆盖用户配额。
    """
    user = User.query.get(user_id)
    if not user:
        raise SubscriptionProvisioningError("user not found")

    plan = Plan.query.filter_by(id=plan_id, is_enabled=True).first()
    if not plan:
        raise SubscriptionProvisioningError("plan not found")

    node = _select_node_for_user(user)
    if not node:
        raise SubscriptionProvisioningError("no enabled node available")

    now = datetime.now(timezone.utc)
    plan_gb = float(traffic_gb)
    dur = int(duration_days)

    xui = XUIClient.from_node(node)

    try:
        exp_ms = int((now + timedelta(days=dur)).timestamp() * 1000)
        total_bytes = _traffic_limit_bytes_from_gb(plan_gb if plan_gb and plan_gb > 0 else None)

        snap_first = xui.get_client_traffic_snapshot(user.email, user.uuid)
        resolved_client_uuid = None
        if user.uuid:
            resolved_client_uuid = user.uuid
        elif snap_first:
            resolved_client_uuid = snap_first.get("client_uuid")

        if resolved_client_uuid:
            link = xui.update_client_quota_raw(
                client_uuid=resolved_client_uuid,
                username=user.username,
                email=user.email,
                total_bytes=total_bytes,
                expiry_time_ms=exp_ms,
            )
            client_uuid = resolved_client_uuid
        else:
            client_uuid, link = xui.create_vless_user(
                user.username,
                user.email,
                total_gb=plan_gb,
                expiry_time_ms=exp_ms,
            )

        snap2 = xui.get_client_traffic_snapshot(user.email, client_uuid)
        if snap2 is None:
            raise SubscriptionProvisioningError("x-ui: cannot read client traffic after provision")

        remaining_gb = _remaining_gb_from_snapshot(
            int(snap2.get("total") or 0),
            int(snap2.get("up") or 0),
            int(snap2.get("down") or 0),
        )
        remaining_gb = _coalesce_remaining_with_order_gb(remaining_gb, plan_gb)
        expires_at = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)

    except XUIClientError as exc:
        raise SubscriptionProvisioningError(str(exc)) from exc

    latest_sub = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if latest_sub:
        latest_sub.started_at = now
        latest_sub.plan_id = plan.id
        latest_sub.expires_at = expires_at
        latest_sub.traffic_limit_gb = plan_gb
        latest_sub.traffic_remaining_gb = remaining_gb
        sub = latest_sub
    else:
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            started_at=now,
            expires_at=expires_at,
            traffic_limit_gb=plan_gb,
            traffic_remaining_gb=remaining_gb,
        )
        db.session.add(sub)

    user.uuid = client_uuid
    user.vless_link = link
    user.current_node_id = node.id
    db.session.commit()

    return ProvisionResult(
        subscription=sub,
        subscription_url=link,
        node_id=node.id,
        node_name=node.name,
        node_region=node.region,
        client_uuid=client_uuid,
    )
