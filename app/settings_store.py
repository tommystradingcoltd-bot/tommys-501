"""Key/value settings with typed defaults, plus fee + postage seed tables.

Every fee/rate here is a *starting default* marked VERIFY. The user must check them
(see SETUP_CHECKLIST.md). They are editable in the dashboard.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeeConfig, PostageRate, Setting, Source

DEFAULT_SETTINGS: dict[str, Any] = {
    "phase_mode": "capital_growth",          # capital_growth | steady
    "phase_started": date.today().isoformat(),
    "starting_capital": 5000.0,
    "capital_reserve": 300.0,
    "min_net_profit": 8.0,
    "large_deal_threshold": 150.0,
    "large_deal_margin_relief": 0.05,
    "low_confidence_min_margin": 0.60,
    "steady_min_margin_override": 0.50,     # capital-growth: >60-day/31-60 tiers alert only if margin >= this
    "listing_quality_uplift": 0.0,          # fraction; learns from real sales
    "fault_return_reserve_pct": 0.05,
    "tier_rules": [
        {"max_days": 14, "min_margin": 0.25},
        {"max_days": 30, "min_margin": 0.30},
        {"max_days": 60, "min_margin": 0.40},
    ],
    "max_days_to_alert": 60,
    "base_location": {"postcode": "M1", "label": "Office (Manchester)", "lat": 53.4794, "lon": -2.2453},
    "collection_max_miles": 40,
    "travel": {"pence_per_mile": 45, "hourly_rate": 12.0, "avg_mph": 30, "handling_minutes": 20},
    "high_priority_score": 70,
    "notify_quiet_hours": "22-07",
    "comp_window_days": 90,
    "valuation_cache_hours": 24,
    "auto_markdown": [{"after_days_pct": 100, "pct_off": 0.05}, {"after_days_pct": 150, "pct_off": 0.10}, {"after_days_pct": 200, "pct_off": 0.15}],
    "clone_rule": {"months": 3, "min_margin": 0.30, "max_avg_days": 30},
    "monthly_buying_capacity": 4000.0,     # £ of stock one person can buy/test/list per month (projections cap)
    "demo_history_loaded": False,
}

# key, group, label, value, unit, notes
DEFAULT_FEES: list[tuple[str, str, str, float, str, str]] = [
    ("ebay_fvf_pct", "sell_fees", "eBay final value fee (video games, private/business)", 12.8, "pct", "Includes payment processing on managed payments; UK private sellers may have 0% promos - VERIFY"),
    ("ebay_fvf_fixed", "sell_fees", "eBay per-order fixed fee", 0.30, "gbp", "VERIFY"),
    ("ebay_regulatory_fee_pct", "sell_fees", "eBay regulatory operating fee", 0.35, "pct", "VERIFY"),
    ("vinted_sell_pct", "sell_fees", "Vinted seller fee", 0.0, "pct", "Vinted charges buyer protection to the buyer - VERIFY"),
    ("vinted_buyer_protection_pct", "buy_fees", "Vinted buyer protection % (when I buy)", 5.0, "pct", "VERIFY"),
    ("vinted_buyer_protection_fixed", "buy_fees", "Vinted buyer protection fixed", 0.70, "gbp", "VERIFY"),
    ("depop_sell_pct", "sell_fees", "Depop seller fee", 10.0, "pct", "VERIFY - Depop moved fees to buyers in 2024 UK"),
    ("depop_buyer_fee_pct", "buy_fees", "Depop buyer fee (when I buy)", 5.0, "pct", "VERIFY"),
    ("shpock_buyer_fee_pct", "buy_fees", "Shpock buyer protection", 5.0, "pct", "VERIFY"),
    ("ebay_buyer_fee_pct", "buy_fees", "eBay buyer protection fee (private sellers, UK)", 4.0, "pct", "Introduced Feb 2025 for private-seller purchases - VERIFY"),
    ("ebay_buyer_fee_fixed", "buy_fees", "eBay buyer protection fixed", 0.75, "gbp", "VERIFY"),
    ("facebook_buyer_fee_pct", "buy_fees", "Facebook Marketplace buyer fee", 0.0, "pct", "Local collection = none"),
    ("gumtree_buyer_fee_pct", "buy_fees", "Gumtree buyer fee", 0.0, "pct", ""),
    ("paypal_pct", "payment", "PayPal goods & services (if used)", 2.9, "pct", "VERIFY"),
    ("paypal_fixed", "payment", "PayPal fixed fee", 0.30, "gbp", "VERIFY"),
    ("packaging_small", "costs", "Packaging: large letter / mailer", 0.40, "gbp", "VERIFY"),
    ("packaging_parcel", "costs", "Packaging: small parcel box + bubble wrap", 0.90, "gbp", "VERIFY"),
    ("packaging_medium", "costs", "Packaging: medium parcel", 1.80, "gbp", "VERIFY"),
    ("fault_return_reserve_pct", "costs", "Fault / return reserve", 5.0, "pct", "Set from your real return rate over time"),
    ("fuel_pence_per_mile", "travel", "Vehicle cost per mile (HMRC 45p rate as proxy)", 45.0, "pence_per_mile", "VERIFY against your real fuel + wear"),
    ("time_hourly_rate", "travel", "Value of my time per hour", 12.0, "gbp_per_hour", "Your call"),
    ("avg_speed_mph", "travel", "Average door-to-door speed", 30.0, "mph", ""),
    ("handling_minutes", "travel", "Collection handling time (minutes)", 20.0, "minutes", ""),
]

# carrier, service, weight_class, max_weight_g, price, tracked, default
DEFAULT_POSTAGE: list[tuple[str, str, str, int, float, bool, bool]] = [
    ("Royal Mail", "2nd Class Large Letter (up to 250g)", "large_letter", 250, 1.55, False, True),
    ("Royal Mail", "1st Class Large Letter (up to 250g)", "large_letter", 250, 2.10, False, False),
    ("Royal Mail", "Tracked 48 Large Letter", "large_letter", 750, 2.70, True, False),
    ("Royal Mail", "Tracked 48 Small Parcel (up to 2kg)", "small_parcel", 2000, 3.35, True, True),
    ("Royal Mail", "Tracked 24 Small Parcel (up to 2kg)", "small_parcel", 2000, 4.15, True, False),
    ("Evri", "ParcelShop Standard (up to 2kg)", "small_parcel", 2000, 3.19, True, False),
    ("Royal Mail", "Tracked 48 Medium Parcel (up to 2kg)", "medium_parcel", 2000, 5.59, True, False),
    ("Royal Mail", "Tracked 48 Medium Parcel (up to 10kg)", "medium_parcel", 10000, 7.29, True, True),
    ("Evri", "ParcelShop Standard (2-5kg)", "medium_parcel", 5000, 5.99, True, False),
    ("Evri", "ParcelShop Standard (5-10kg)", "medium_parcel", 10000, 8.99, True, False),
    ("Royal Mail", "Tracked 48 Large Parcel (up to 20kg)", "large_parcel", 20000, 12.95, True, True),
]

DEFAULT_SOURCES: list[dict] = [
    dict(slug="ebay", name="eBay UK", kind="api", enabled=True, poll_interval_min=10, buyer_fee_pct=4.0, buyer_fee_fixed=0.75),
    dict(slug="facebook", name="Facebook Marketplace", kind="browser", enabled=False, poll_interval_min=30),
    dict(slug="vinted", name="Vinted", kind="browser", enabled=False, poll_interval_min=20, buyer_fee_pct=5.0, buyer_fee_fixed=0.70),
    dict(slug="gumtree", name="Gumtree", kind="browser", enabled=False, poll_interval_min=30),
    dict(slug="shpock", name="Shpock", kind="browser", enabled=False, poll_interval_min=30, buyer_fee_pct=5.0),
    dict(slug="depop", name="Depop", kind="browser", enabled=False, poll_interval_min=30, buyer_fee_pct=5.0),
    dict(slug="paid_feed", name="Paid data provider (stub)", kind="paid", enabled=False, poll_interval_min=15),
]


def seed_defaults(db: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))
    existing = {f.key for f in db.scalars(select(FeeConfig))}
    for key, group, label, value, unit, notes in DEFAULT_FEES:
        if key not in existing:
            db.add(FeeConfig(key=key, group=group, label=label, value=value, unit=unit, notes=notes, verify_flag=True))
    if db.scalar(select(PostageRate).limit(1)) is None:
        for carrier, service, wc, maxg, price, tracked, default in DEFAULT_POSTAGE:
            db.add(PostageRate(carrier=carrier, service=service, weight_class=wc, max_weight_g=maxg, price=price,
                               tracked=tracked, default_for_class=default, verify_flag=True))
    existing_sources = {s.slug for s in db.scalars(select(Source))}
    for src in DEFAULT_SOURCES:
        if src["slug"] not in existing_sources:
            db.add(Source(**src))
    db.flush()


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.flush()


def all_settings(db: Session) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    for row in db.scalars(select(Setting)):
        out[row.key] = row.value
    return out


def fee_map(db: Session) -> dict[str, float]:
    return {f.key: f.value for f in db.scalars(select(FeeConfig))}


def postage_map(db: Session) -> dict[str, float]:
    """weight_class -> default price (cheapest default per class)."""
    out: dict[str, float] = {}
    for r in db.scalars(select(PostageRate).order_by(PostageRate.price)):
        if r.default_for_class and r.weight_class not in out:
            out[r.weight_class] = r.price
    for r in db.scalars(select(PostageRate).order_by(PostageRate.price)):
        out.setdefault(r.weight_class, r.price)
    return out
