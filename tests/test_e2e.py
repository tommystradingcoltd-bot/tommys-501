"""Listing comes in -> valued -> scored -> alert 'sent' (mock) -> bought -> listed -> sold -> P&L updates."""
from sqlalchemy import select

from app.analytics.pnl import accuracy, cash_available, pnl_by, realised_profit, stock_value_at_cost
from app.inventory.listing_gen import generate_listing
from app.inventory.service import list_on_ebay, mark_bought, record_sale, set_status
from app.inventory.testing import record_test
from app.models import Alert, Deal, NormalisedItem, Source, Valuation
from app.pipeline import process_listing
from app.sourcing.base import RawListing
from app.sourcing.runner import persist_listing, run_source
from app.identification.valuation import seed_mock_comps
from datetime import datetime


def test_end_to_end(db, niche, notifier):
    from app.settings_store import set_setting
    set_setting(db, "notify_quiet_hours", "")
    seed_mock_comps(db, niche)
    ebay = db.scalar(select(Source).where(Source.slug == "ebay"))
    rl = RawListing(source="ebay", external_id="e2e-1", url="https://www.ebay.co.uk/itm/e2e-1",
                    title="Conker's Bad Fur Day N64 PAL cartridge", description="Genuine cart, tested, label mint.",
                    price=30.0, postage_cost=2.5, seller_feedback=400)
    row, is_new = persist_listing(db, ebay, niche, rl)
    assert is_new
    deal = process_listing(db, row)
    assert deal.item.platform == "N64" and deal.item.title == "Conker's Bad Fur Day"
    assert deal.valuation.sold_count > 0 and deal.expected_sale_price > 60
    assert deal.should_alert and deal.score > 0 and deal.status == "alerted"
    alert = db.scalar(select(Alert).where(Alert.deal_id == deal.id))
    assert alert is not None
    if deal.priority == "high":
        assert alert.status == "sent" and notifier.sent[-1].url.endswith(f"/deals/{deal.id}")
    else:
        assert alert.status == "pending"
    cash0 = cash_available(db)
    inv = mark_bought(db, deal)
    assert stock_value_at_cost(db) == inv.cost_basis and cash_available(db) < cash0
    set_status(db, inv, "testing")
    record_test(db, inv, {"boots": "pass", "saves": "pass", "label_auth": "pass", "pcb_auth": "pass", "region": "pass", "disc_grade": "na", "contents": "na"})
    listing = generate_listing(db, inv)
    list_on_ebay(db, listing)
    assert inv.status == "listed"
    sale = record_sale(db, inv, "ebay", 90.0, 11.8, postage_cost=1.55, packaging_cost=0.4)
    assert inv.status == "sold" and sale.net_profit > 0
    now = datetime.utcnow()
    assert realised_profit(db, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now.replace(year=now.year + 1)) == sale.net_profit
    rows = pnl_by(db, "source")
    assert rows[0]["key"] == "ebay" and rows[0]["profit"] == sale.net_profit and rows[0]["predicted_profit"] == deal.net_profit
    assert accuracy(db)["count"] == 1
    assert stock_value_at_cost(db) == 0


def test_run_source_pauses_on_login_wall(db, niche):
    from pathlib import Path
    from app.sourcing.browser.helper import FixtureBrowserWatcher
    vinted = db.scalar(select(Source).where(Source.slug == "vinted"))
    vinted.enabled = True
    html = (Path(__file__).parent / "fixtures" / "html" / "vinted_login_wall.html").read_text()
    stats = run_source(db, vinted, [niche], watcher=FixtureBrowserWatcher("vinted", html), process=process_listing)
    assert "paused" in stats and vinted.status == "needs_login"
    stats = run_source(db, vinted, [niche], watcher=FixtureBrowserWatcher("vinted", html), process=process_listing)
    assert stats.get("skipped") == "needs_login"


def test_run_source_with_fixture_creates_deals(db, niche):
    from pathlib import Path
    from app.sourcing.browser.helper import FixtureBrowserWatcher
    seed_mock_comps(db, niche)
    gumtree = db.scalar(select(Source).where(Source.slug == "gumtree"))
    gumtree.enabled = True
    html = (Path(__file__).parent / "fixtures" / "html" / "gumtree_search.html").read_text()
    stats = run_source(db, gumtree, [niche], watcher=FixtureBrowserWatcher("gumtree", html), process=process_listing, max_queries=1)
    assert stats["new"] == 3 and gumtree.status == "ok"
    deals = db.scalars(select(Deal)).all()
    assert len(deals) == 3 and all(d.collection_only for d in deals) and all(d.distance_miles is not None for d in deals)
    assert db.query(NormalisedItem).count() == 3 and db.query(Valuation).count() >= 1


def test_purge_personal_data(db, niche):
    from datetime import timedelta
    from app.pipeline import load_seed_listings, purge_personal_data
    deals = load_seed_listings(db, niche, notify=False)
    for d in deals[:5]:
        d.status = "passed"
        d.created_at = datetime.utcnow() - timedelta(days=100)
    deals[0].status = "bought"
    assert purge_personal_data(db, 90) == 4
    assert deals[1].raw_listing.seller_name == "" and deals[1].raw_listing.status == "purged"
    assert deals[0].raw_listing.status != "purged"
