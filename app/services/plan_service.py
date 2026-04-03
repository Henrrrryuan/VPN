from decimal import Decimal

from app.extensions import db
from app.models import Plan

# 与 dashboard 定价表、X-UI 开通流量一致：Basic / Pro / Premium → 80 / 150 / 200 GB
CANONICAL_PLANS = (
    ("Basic", Decimal("29.00"), 80.0),
    ("Pro", Decimal("49.00"), 150.0),
    ("Premium", Decimal("69.00"), 200.0),
)


def bootstrap_plans_if_needed() -> None:
    if Plan.query.count() > 0:
        return
    for name, price, gb in CANONICAL_PLANS:
        db.session.add(
            Plan(
                name=name,
                price=price,
                traffic_limit_gb=gb,
                duration_days=30,
                is_enabled=True,
            )
        )
    db.session.commit()


def ensure_canonical_plans() -> None:
    """将 Basic/Pro/Premium 的流量与价格与产品页对齐；库中已有记录也会被更新。"""
    changed = False
    for name, price, gb in CANONICAL_PLANS:
        p = Plan.query.filter_by(name=name).first()
        if not p:
            continue
        if float(p.traffic_limit_gb) != gb or p.price != price:
            p.traffic_limit_gb = gb
            p.price = price
            changed = True
    if changed:
        db.session.commit()
