"""Inventory lifecycle: bought -> stock -> tested -> listed -> sold -> shipped. Capital ledger + P&L hooks."""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.pnl import post_ledger
from app.inventory.ebay_sell import get_ebay_sell
from app.inventory.listing_gen import generate_listing
from app.inventory.sku import next_sku
from app.models import Deal, InventoryItem, Listing, Niche, PlatformListing, Sale, Task, INVENTORY_STATUSES
from app.notify.service import notify_task
from app.profit.engine import weight_class_for

log = logging.getLogger(__name__)

TRANSITIONS = {s: INVENTORY_STATUSES[i + 1:] for i, s in enumerate(INVENTORY_STATUSES)}
TRANSITIONS["returned"] = ["testing", "ready_to_photograph", "listed"]


def mark_bought(db: Session, deal: Deal, actual_price: float | None = None, notes: str = "") -> InventoryItem:
    niche = db.get(Niche, deal.niche_id)
    item_n = deal.item
    price = actual_price if actual_price is not None else deal.buy_price
    landed = round(price + deal.buyer_fees + deal.inbound_cost, 2)
    inv = InventoryItem(
        sku=next_sku(db, niche.slug, item_n.platform), deal_id=deal.id, normalised_item_id=item_n.id, niche_id=niche.id,
        title=item_n.title if item_n.title != "bundle" else deal.raw_listing.title[:200], platform=item_n.platform,
        category=item_n.category, completeness=item_n.completeness, region=item_n.region, source=deal.raw_listing.source.slug,
        cost_basis=landed, purchase_price=price, purchase_date=date.today(), status="in_transit" if not deal.collection_only else "testing",
        expected_sale_price=deal.expected_sale_price, expected_days_to_sell=deal.est_days_to_sell, expected_net_profit=deal.net_profit,
        weight_class=weight_class_for(niche.config or {}, item_n.category, item_n.completeness, item_n.is_bundle), notes=notes,
    )
    db.add(inv)
    deal.status = "bought"
    deal.decided_at = datetime.utcnow()
    db.flush()
    post_ledger(db, "purchase", -landed, "inventory_item", inv.id, f"Bought {inv.sku} {inv.title[:40]}")
    return inv


def set_status(db: Session, item: InventoryItem, new_status: str) -> InventoryItem:
    if new_status not in INVENTORY_STATUSES:
        raise ValueError(f"unknown status {new_status}")
    item.status = new_status
    if new_status == "listed" and not item.listed_at:
        item.listed_at = datetime.utcnow()
    if new_status == "returned":
        _flag_task(db, "return", f"Return received: {item.sku}", f"Re-test {item.title} and relist or write off.", "inventory_item", item.id)
    db.flush()
    return item


def list_on_ebay(db: Session, listing: Listing, image_urls: list[str] | None = None) -> PlatformListing:
    client = get_ebay_sell()
    item = listing.item
    pub = client.publish(item.sku, listing.title, listing.description, listing.price, listing.item_specifics, "used", image_urls or [])
    pl = PlatformListing(listing_id=listing.id, platform="ebay", external_id=pub.external_id, url=pub.url, price=listing.price, status="active")
    db.add(pl)
    listing.status = "active"
    set_status(db, item, "listed")
    db.flush()
    return pl


def add_platform_listing(db: Session, listing: Listing, platform: str, external_id: str = "", url: str = "", price: float | None = None) -> PlatformListing:
    pl = PlatformListing(listing_id=listing.id, platform=platform, external_id=external_id, url=url, price=price or listing.price, status="active")
    db.add(pl)
    listing.status = "active"
    set_status(db, listing.item, "listed")
    db.flush()
    return pl


def record_sale(db: Session, item: InventoryItem, platform: str, sale_price: float, platform_fees: float, payment_fees: float = 0.0,
                postage_cost: float = 0.0, packaging_cost: float = 0.0, postage_charged: float = 0.0, other_costs: float = 0.0,
                external_order_id: str = "", sold_at: datetime | None = None, source: str = "manual") -> Sale:
    sold_at = sold_at or datetime.utcnow()
    start = item.listed_at or datetime.combine(item.purchase_date, datetime.min.time())
    days = max(0, (sold_at - start).days)
    net = round(sale_price + postage_charged - item.cost_basis - platform_fees - payment_fees - postage_cost - packaging_cost - other_costs, 2)
    sale = Sale(inventory_item_id=item.id, platform=platform, external_order_id=external_order_id, sale_price=sale_price,
                postage_charged=postage_charged, platform_fees=platform_fees, payment_fees=payment_fees, postage_cost=postage_cost,
                packaging_cost=packaging_cost, other_costs=other_costs, net_profit=net,
                net_margin=round(net / sale_price, 4) if sale_price else 0.0, days_to_sell=days, sold_at=sold_at, source=source)
    db.add(sale)
    item.status = "sold"
    item.sold_at = sold_at
    db.flush()
    post_ledger(db, "sale", round(sale_price + postage_charged - platform_fees - payment_fees - postage_cost - packaging_cost - other_costs, 2),
                "sale", sale.id, f"Sold {item.sku} on {platform}")
    _remove_from_other_platforms(db, item, platform)
    return sale


def _remove_from_other_platforms(db: Session, item: InventoryItem, sold_platform: str) -> None:
    """Flag an urgent task; end eBay listings automatically through the API."""
    others = []
    for listing in item.listings:
        for pl in listing.platform_listings:
            if pl.status != "active":
                continue
            if pl.platform == sold_platform:
                pl.status, pl.ended_at = "sold", datetime.utcnow()
            elif pl.platform == "ebay":
                ok = get_ebay_sell().end(pl.external_id)
                pl.status, pl.ended_at = ("ended" if ok else "remove_pending"), datetime.utcnow()
                if not ok:
                    others.append(pl.platform)
            else:
                pl.status = "remove_pending"
                others.append(pl.platform)
        listing.status = "sold"
    if others:
        task = _flag_task(db, "remove_listings", f"URGENT: remove {item.sku} from {', '.join(sorted(set(others)))}",
                          f"{item.title} sold on {sold_platform}. End the other listings now to avoid a double sale.", "inventory_item", item.id, urgent=True)
        notify_task(db, task.title, task.detail)


def _flag_task(db: Session, kind: str, title: str, detail: str, ref_type: str, ref_id: int, urgent: bool = False) -> Task:
    t = Task(kind=kind, title=title[:200], detail=detail, urgent=urgent, ref_type=ref_type, ref_id=ref_id)
    db.add(t)
    db.flush()
    return t


def mark_platform_removed(db: Session, pl: PlatformListing) -> None:
    pl.status, pl.ended_at = "ended", datetime.utcnow()
    item = pl.listing.item
    pending = [p for l in item.listings for p in l.platform_listings if p.status == "remove_pending"]
    if not pending:
        for t in db.scalars(select(Task).where(Task.kind == "remove_listings", Task.ref_id == item.id, Task.done == False)):  # noqa: E712
            t.done, t.done_at = True, datetime.utcnow()
    db.flush()


def mark_shipped(db: Session, item: InventoryItem) -> None:
    item.status = "shipped"
    for s in item.sales:
        if not s.shipped_at:
            s.shipped_at = datetime.utcnow()
    db.flush()


def sync_ebay_sales(db: Session, since: datetime) -> int:
    """Pull orders from the Fulfilment API and record sales for matching SKUs."""
    client = get_ebay_sell()
    n = 0
    for o in client.fetch_orders(since.strftime("%Y-%m-%dT%H:%M:%S.000Z")):
        item = db.scalar(select(InventoryItem).where(InventoryItem.sku == o.get("sku", ""), InventoryItem.status == "listed"))
        if not item:
            continue
        if db.scalar(select(Sale.id).where(Sale.external_order_id == o["order_id"])):
            continue
        record_sale(db, item, "ebay", o["price"], o.get("fees", 0.0), postage_charged=o.get("postage_charged", 0.0),
                    external_order_id=o["order_id"], sold_at=datetime.fromisoformat(o["sold_at"].replace("Z", "+00:00")).replace(tzinfo=None),
                    source="ebay_fulfilment")
        n += 1
    return n


def create_listing_for(db: Session, item: InventoryItem) -> Listing:
    return generate_listing(db, item)
