from decimal import Decimal

from app.extensions import db
from app.models import Plan


def bootstrap_plans_if_needed() -> None:
    if Plan.query.count() > 0:
        return
    defaults = [
        Plan(
            name="Basic",
            price=Decimal("9.99"),
            traffic_limit_gb=100.0,
            duration_days=30,
            is_enabled=True,
        ),
        Plan(
            name="Pro",
            price=Decimal("19.99"),
            traffic_limit_gb=300.0,
            duration_days=30,
            is_enabled=True,
        ),
        Plan(
            name="Premium",
            price=Decimal("39.99"),
            traffic_limit_gb=1000.0,
            duration_days=30,
            is_enabled=True,
        ),
    ]
    for p in defaults:
        db.session.add(p)
    db.session.commit()
