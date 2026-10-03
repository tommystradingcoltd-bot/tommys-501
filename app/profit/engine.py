"""Profit engine: full landed P&L for a listing. Pure functions; config passed in explicitly."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from app.profit.distance import collection_cost


@dataclass
class FeeTable:
    """All percentages are fractions (0.128 = 12.8%)."""
    buy_fee_pct: float = 0.0          # buyer protection on the buying platform
    buy_fee_fixed: float = 0.0
    sell_fee_pct: float = 0.128       # eBay FVF
    sell_fee_fixed: float = 0.30
    sell_regulatory_pct: float = 0.0035
    payment_pct: float = 0.0          # 0 when included in platform fee (eBay managed payments)
    payment_fixed: float = 0.0
    packaging: float = 0.90
    reserve_pct: float = 0.05
    pence_per_mile: float = 45.0
    hourly_rate: float = 12.0
    avg_mph: float = 30.0
    handling_minutes: float = 20.0


@dataclass
class DealInput:
    buy_price: float
    expected_sale_price: float
    inbound_postage: Optional[float] = None   # None = unknown -> estimated from outbound rate
    collection_only: bool = False
    distance_miles: Optional[float] = None    # one-way
    outbound_postage: float = 3.35
    listing_uplift: float = 0.0               # my listing-quality uplift %, learned from sales
    postage_charged_to_buyer: float = 0.0     # if I charge postage separately, it offsets outbound cost
    bundle_item_count: int = 1


@dataclass
class PnL:
    buy_price: float
    buyer_fees: float
    inbound_cost: float
    landed_cost: float
    expected_sale_price: float
    sell_fees: float
    payment_fees: float
    outbound_postage: float
    packaging: float
    reserve: float
    total_sell_costs: float
    net_profit: float
    net_margin: float
    roi: float
    collection_cost: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def calculate(inp: DealInput, fees: FeeTable) -> PnL:
    notes: list[str] = []
    buyer_fees = round(inp.buy_price * fees.buy_fee_pct + (fees.buy_fee_fixed if inp.buy_price > 0 else 0), 2)
    coll_cost = 0.0
    if inp.collection_only:
        if inp.distance_miles is None:
            inbound = 0.0
            notes.append("collection only, distance unknown")
        else:
            coll_cost = collection_cost(inp.distance_miles, fees.pence_per_mile, fees.hourly_rate, fees.avg_mph, fees.handling_minutes)
            inbound = coll_cost
    elif inp.inbound_postage is None:
        inbound = inp.outbound_postage
        notes.append("inbound postage unknown, assumed same as outbound")
    else:
        inbound = inp.inbound_postage
    landed = round(inp.buy_price + buyer_fees + inbound, 2)

    sale = round(inp.expected_sale_price * (1 + inp.listing_uplift), 2)
    gross_received = sale + inp.postage_charged_to_buyer
    sell_fees = round(gross_received * (fees.sell_fee_pct + fees.sell_regulatory_pct) + fees.sell_fee_fixed, 2) if sale > 0 else 0.0
    payment_fees = round(gross_received * fees.payment_pct + (fees.payment_fixed if sale > 0 else 0), 2)
    # Bundles bought to split: each item posted separately
    n = max(1, inp.bundle_item_count)
    outbound = round(inp.outbound_postage * n - inp.postage_charged_to_buyer, 2)
    packaging = round(fees.packaging * n, 2)
    if n > 1:
        sell_fees = round(sell_fees + fees.sell_fee_fixed * (n - 1), 2)
        notes.append(f"bundle split into {n} lots: fixed fee, postage and packaging counted {n}x")
    reserve = round(sale * fees.reserve_pct, 2)
    total_sell_costs = round(sell_fees + payment_fees + outbound + packaging + reserve, 2)
    net = round(sale - landed - total_sell_costs, 2)
    margin = round(net / sale, 4) if sale > 0 else -1.0
    roi = round(net / landed, 4) if landed > 0 else 0.0
    return PnL(
        buy_price=inp.buy_price, buyer_fees=buyer_fees, inbound_cost=round(inbound, 2), landed_cost=landed,
        expected_sale_price=sale, sell_fees=sell_fees, payment_fees=payment_fees, outbound_postage=outbound,
        packaging=packaging, reserve=reserve, total_sell_costs=total_sell_costs, net_profit=net, net_margin=margin,
        roi=roi, collection_cost=coll_cost, notes=notes,
    )


def fee_table_from_config(fees: dict[str, float], source_slug: str, sell_platform: str = "ebay",
                          weight_class: str = "small_parcel") -> FeeTable:
    """Build a FeeTable from the fee_config rows (percent values are stored as whole numbers, e.g. 12.8)."""
    g = lambda k, d=0.0: float(fees.get(k, d))  # noqa: E731
    pk = {"large_letter": "packaging_small", "small_parcel": "packaging_parcel", "medium_parcel": "packaging_medium", "large_parcel": "packaging_medium"}
    buy_pct = g(f"{source_slug}_buyer_fee_pct", g(f"{source_slug}_buyer_protection_pct", 0.0))
    buy_fixed = g(f"{source_slug}_buyer_fee_fixed", g(f"{source_slug}_buyer_protection_fixed", 0.0))
    sell_pct = g(f"{sell_platform}_fvf_pct", g(f"{sell_platform}_sell_pct", 12.8))
    return FeeTable(
        buy_fee_pct=buy_pct / 100, buy_fee_fixed=buy_fixed, sell_fee_pct=sell_pct / 100,
        sell_fee_fixed=g(f"{sell_platform}_fvf_fixed", 0.0), sell_regulatory_pct=g(f"{sell_platform}_regulatory_fee_pct", 0.0) / 100,
        payment_pct=0.0 if sell_platform == "ebay" else g("paypal_pct", 0.0) / 100,
        payment_fixed=0.0 if sell_platform == "ebay" else g("paypal_fixed", 0.0),
        packaging=g(pk.get(weight_class, "packaging_parcel"), 0.9), reserve_pct=g("fault_return_reserve_pct", 5.0) / 100,
        pence_per_mile=g("fuel_pence_per_mile", 45.0), hourly_rate=g("time_hourly_rate", 12.0), avg_mph=g("avg_speed_mph", 30.0),
        handling_minutes=g("handling_minutes", 20.0),
    )


def weight_class_for(niche_cfg: dict, category: str, completeness: str, is_bundle: bool) -> str:
    classes = niche_cfg.get("postage_classes", {})
    if is_bundle:
        return classes.get("bundle", "medium_parcel")
    if category == "console":
        return classes.get("console", "medium_parcel")
    if category == "accessory":
        return classes.get("accessory", "small_parcel")
    if completeness in ("loose",):
        return classes.get("game_loose", "large_letter")
    return classes.get("game_boxed", "small_parcel")
