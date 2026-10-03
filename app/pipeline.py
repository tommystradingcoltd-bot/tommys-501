"""Pipeline: raw listing -> normalise -> risk -> valuation -> P&L -> rules -> alert.

`process_listing(db, row)` is the single entry point used by the source runner, the seed loader and tests.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.pnl import cash_available
from app.identification.normaliser import normalise_listing
from app.identification.risk import assess_risk, max_severity
from app.identification.valuation import value_bundle, value_item
from app.models import Deal, Niche, RawListing, Source
from app.notify.service import queue_deal_alert
from app.profit.distance import road_miles
from app.profit.engine import DealInput, calculate, fee_table_from_config, weight_class_for
from app.profit.rules import RuleConfig, evaluate
from app.settings_store import all_settings, fee_map, postage_map

log = logging.getLogger(__name__)
HARD_BLOCK_CODES = {"repro", "too_good", "stolen_signals"}   # never alert on these, whatever the margin


def process_listing(db: Session, row: RawListing, providers=None, notify: bool = True) -> Deal:
    niche: Niche = row.niche
    source: Source = row.source
    cfg = niche.config or {}
    settings = all_settings(db)
    fees = fee_map(db)
    postage = postage_map(db)

    item = normalise_listing(db, row, niche)

    # Valuation (bundle = sum of parts)
    if item.is_bundle and item.bundle_items:
        total, est_days, conf, parts = value_bundle(db, niche, item.bundle_items, providers)
        valuation = None
        expected, confidence = total, conf
        n_items = len(parts)
        breakdown_val = {"bundle_parts": parts}
    else:
        valuation = value_item(db, niche, item.platform, item.title, item.region, item.completeness, providers)
        expected, est_days, confidence = valuation.median_price, valuation.est_days_to_sell, valuation.confidence
        n_items = 1
        breakdown_val = {"sold_count": valuation.sold_count, "active_count": valuation.active_count,
                         "p25": valuation.p25, "p75": valuation.p75, "sell_through": valuation.sell_through_rate}
    if item.is_bundle and not item.bundle_items:
        confidence = "low"

    # Risk flags (needs the median for the too-good check)
    item.risk_flags = assess_risk(row, item, niche, expected or None, source.slug)
    severity = max_severity(item.risk_flags)

    # Distance for collection-only
    distance = None
    if row.collection_only:
        distance = road_miles(settings.get("base_location", {}), row.postcode_district, row.location_text)

    # P&L
    weight_class = weight_class_for(cfg, item.category, item.completeness, item.is_bundle)
    ft = fee_table_from_config(fees, source.slug, "ebay", weight_class)
    part_class = weight_class_for(cfg, "game", "loose", False) if item.is_bundle else weight_class
    outbound = postage.get(part_class if item.is_bundle else weight_class, 3.35)
    inp = DealInput(
        buy_price=row.price, expected_sale_price=expected, inbound_postage=row.postage_cost,
        collection_only=row.collection_only, distance_miles=distance, outbound_postage=outbound,
        listing_uplift=float(settings.get("listing_quality_uplift", 0.0)), bundle_item_count=n_items,
    )
    if row.collection_only and distance is None:
        inp.inbound_postage = 0.0
    pnl = calculate(inp, ft)

    # Rules
    rc = RuleConfig.from_settings(settings)
    cash = cash_available(db)
    decision = evaluate(pnl.net_profit, pnl.net_margin, est_days, confidence, row.price, pnl.landed_cost, cash, rc)
    skip = ""
    hard_block = [f["label"] for f in item.risk_flags if f["code"] in HARD_BLOCK_CODES]
    if not decision.should_alert:
        skip = decision.reason
    elif hard_block:
        decision.should_alert = False
        skip = "blocked by risk flag: " + "; ".join(hard_block)
    elif severity == "high" and pnl.net_margin < rc.low_confidence_min_margin:
        decision.should_alert = False
        skip = "high-severity risk flag: " + "; ".join(f["label"] for f in item.risk_flags if f["severity"] == "high")
    elif severity == "high":
        decision.check_manually = True
    if row.collection_only and distance is not None and distance > float(settings.get("collection_max_miles", 40)) and decision.should_alert:
        if pnl.net_margin < rc.low_confidence_min_margin:
            decision.should_alert = False
            skip = f"collection {distance:.0f} miles away exceeds the {settings.get('collection_max_miles', 40)}-mile limit"
        else:
            decision.check_manually = True

    deal = Deal(
        raw_listing_id=row.id, normalised_item_id=item.id, valuation_id=valuation.id if valuation else None, niche_id=niche.id,
        buy_price=row.price, buyer_fees=pnl.buyer_fees, inbound_cost=pnl.inbound_cost, landed_cost=pnl.landed_cost,
        expected_sale_price=pnl.expected_sale_price, sell_fees=pnl.sell_fees + pnl.payment_fees, outbound_postage=pnl.outbound_postage,
        packaging=pnl.packaging, reserve=pnl.reserve, net_profit=pnl.net_profit, net_margin=pnl.net_margin, roi=pnl.roi,
        est_days_to_sell=est_days, tier=decision.tier, score=decision.score, distance_miles=distance,
        collection_only=row.collection_only, check_manually=decision.check_manually, capital_warning=decision.capital_warning,
        should_alert=decision.should_alert, skip_reason=skip[:200], priority=decision.priority if decision.should_alert else "low",
        breakdown={**pnl.as_dict(), **breakdown_val, "confidence": confidence, "weight_class": weight_class,
                   "min_margin_required": decision.min_margin_required, "rule_reason": decision.reason, "cash_available": cash},
        status="new",
    )
    db.add(deal)
    row.status = "processed"
    db.flush()
    if deal.should_alert and notify:
        queue_deal_alert(db, deal)
    log.info("deal %s: %s %s buy £%.2f net £%.2f (%.0f%%) %sd score %.0f alert=%s %s", deal.id, item.platform, item.title,
             row.price, pnl.net_profit, pnl.net_margin * 100, est_days, deal.score, deal.should_alert, skip)
    return deal


def load_seed_listings(db: Session, niche: Niche, notify: bool = False) -> list[Deal]:
    """Persist the 50 seed listings through the real pipeline (mock LLM/valuation)."""
    from sqlalchemy import select
    from app.identification.valuation import seed_mock_comps
    from app.seed import seed_listings
    from app.sourcing.runner import persist_listing

    seed_mock_comps(db, niche)
    sources = {s.slug: s for s in db.scalars(select(Source))}
    deals = []
    for rl in seed_listings():
        src = sources.get(rl.source)
        if not src:
            continue
        row, is_new = persist_listing(db, src, niche, rl)
        if is_new and row.status != "duplicate":
            deals.append(process_listing(db, row, notify=notify))
    db.flush()
    return deals


def purge_personal_data(db: Session, retention_days: int) -> int:
    """GDPR-ish hygiene: strip seller names/locations from listings I passed on (or never acted on) after N days."""
    from datetime import timedelta
    from sqlalchemy import select
    db.flush()
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    n = 0
    for deal in db.scalars(select(Deal).where(Deal.status.in_(["passed", "new", "alerted", "expired"]), Deal.created_at < cutoff)):
        rl = deal.raw_listing
        if rl.status != "purged":
            rl.seller_name, rl.location_text, rl.description, rl.raw = "", "", "", {}
            rl.status = "purged"
            n += 1
    db.flush()
    return n
