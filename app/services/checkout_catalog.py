"""
结账页「套餐 × 周期」与后端订单校验一致：价格、流量、天数。
周期 key 与前端 CYCLES[].key 一致：weekly / monthly / quarterly / half / yearly。
"""

from decimal import Decimal
from typing import Dict, Optional, Tuple

# 与 templates/checkout.html PRICES 对齐
_CHECKOUT_PRICES: Dict[Tuple[str, str], Decimal] = {
    ("starter", "weekly"): Decimal("12"),
    ("starter", "monthly"): Decimal("29"),
    ("starter", "quarterly"): Decimal("79"),
    ("starter", "half"): Decimal("149"),
    ("starter", "yearly"): Decimal("279"),
    ("standard", "weekly"): Decimal("19"),
    ("standard", "monthly"): Decimal("49"),
    ("standard", "quarterly"): Decimal("129"),
    ("standard", "half"): Decimal("249"),
    ("standard", "yearly"): Decimal("469"),
    ("pro", "weekly"): Decimal("25"),
    ("pro", "monthly"): Decimal("69"),
    ("pro", "quarterly"): Decimal("179"),
    ("pro", "half"): Decimal("349"),
    ("pro", "yearly"): Decimal("669"),
}

TIER_TO_PLAN_NAME = {"starter": "Basic", "standard": "Pro", "pro": "Premium"}

TIER_MONTHLY_GB = {"starter": 80.0, "standard": 150.0, "pro": 200.0}
TIER_WEEKLY_GB = {"starter": 18.0, "standard": 35.0, "pro": 47.0}

PERIOD_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 90, "half": 183, "yearly": 365}

PERIOD_LABELS = {
    "weekly": "周付",
    "monthly": "月付",
    "quarterly": "季付",
    "half": "半年",
    "yearly": "年付",
}

TIER_LABELS = {"starter": "Starter", "standard": "Standard", "pro": "Pro"}

# 库内 Plan.name → 结账 tier slug（用于按流量反推周期）
PLAN_NAME_TO_TIER = {"Basic": "starter", "Pro": "standard", "Premium": "pro"}

VALID_TIERS = frozenset(TIER_TO_PLAN_NAME)
VALID_PERIODS = frozenset(PERIOD_DAYS)

# 与 templates/recharge.html PACKS 对齐（流量包 · 人工审核收款）
RECHARGE_PACK_PRICES: Dict[int, Decimal] = {
    50: Decimal("15"),
    100: Decimal("25"),
    200: Decimal("45"),
}
VALID_RECHARGE_PACK_GB = frozenset(RECHARGE_PACK_PRICES.keys())


def expected_recharge_pack_amount(traffic_gb: int) -> Optional[Decimal]:
    return RECHARGE_PACK_PRICES.get(int(traffic_gb))

# 与周期对应的流量额度展示后缀（如 47GB/周）
TRAFFIC_PERIOD_SUFFIX = {
    "weekly": "/周",
    "monthly": "/月",
    "quarterly": "/季",
    "half": "/半年",
    "yearly": "/年",
}


def _format_gb_number(gb: float) -> str:
    x = float(gb)
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s or "0"


def format_traffic_quota_display(period_key: str, traffic_gb: float) -> str:
    """例如 weekly + 47 → 「47GB/周」。"""
    suf = TRAFFIC_PERIOD_SUFFIX.get(period_key, "")
    return f"{_format_gb_number(traffic_gb)}GB{suf}"


def infer_period_key_for_traffic(tier: str, traffic_gb: float) -> Optional[str]:
    """根据本周期流量额度反推 period_key（无订单记录时的回退）。"""
    if tier not in VALID_TIERS:
        return None
    tg = float(traffic_gb)
    for pk in PERIOD_DAYS:
        if pk not in VALID_PERIODS:
            continue
        try:
            t, _ = resolve_traffic_and_duration(tier, pk)
        except ValueError:
            continue
        if abs(float(t) - tg) < 0.06:
            return pk
    return None


def expected_amount(tier: str, period_key: str) -> Optional[Decimal]:
    return _CHECKOUT_PRICES.get((tier, period_key))


def resolve_traffic_and_duration(tier: str, period_key: str) -> Tuple[float, int]:
    if tier not in TIER_MONTHLY_GB or period_key not in PERIOD_DAYS:
        raise ValueError("invalid tier or period")
    days = PERIOD_DAYS[period_key]
    if period_key == "weekly":
        return float(TIER_WEEKLY_GB[tier]), days
    monthly = TIER_MONTHLY_GB[tier]
    traffic = round(monthly * (days / 30.0), 2)
    return traffic, days
