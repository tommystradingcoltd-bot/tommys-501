from app.inventory.crosslist import listings_csv
from app.inventory.labels import label_pdf
from app.inventory.listing_gen import build_title, generate_listing, markdown_schedule, rule_based_copy, suggested_price
from app.inventory.service import add_platform_listing, list_on_ebay, mark_bought, mark_platform_removed, record_sale, set_status
from app.inventory.sku import next_sku
from app.inventory.testing import checklist_for, record_test
from app.models import Task
from app.pipeline import load_seed_listings


def test_sku_sequence(db):
    a = next_sku(db, "retro_games", "SNES")
    assert a.startswith("RG-SNES-") and a.endswith("-0001")


def test_title_limit_and_repro_honesty():
    t = build_title("Game Boy Advance", "Pokemon Emerald Version Extremely Long Title That Goes On And On Forever", "PAL", "cib", ["Tested & Working", "Retro Nintendo"])
    assert len(t) <= 80
    copy = rule_based_copy({"platform": "SNES", "title": "Chrono Trigger", "completeness": "loose", "region": "PAL", "category": "game",
                            "condition_notes": "reproduction cartridge", "accessories": []}, [])
    assert "REPRODUCTION" in copy["title"] and "reproduction" in copy["condition_description"].lower()
    assert "genuine" not in copy["condition_description"].lower()


def test_price_and_markdowns():
    assert suggested_price(50) == 51.99
    sched = markdown_schedule(50, 20, [{"after_days_pct": 100, "pct_off": 0.05}, {"after_days_pct": 150, "pct_off": 0.10}])
    assert sched == [{"day": 20, "price": 47.5, "pct_off": 0.05}, {"day": 30, "price": 45.0, "pct_off": 0.10}]


def test_checklist_per_category(niche):
    keys = {c["key"] for c in checklist_for(niche, "game")}
    assert {"boots", "saves", "label_auth", "pcb_auth", "disc_grade", "region"} <= keys
    assert "powers_on" in {c["key"] for c in checklist_for(niche, "console")}
    assert {"powers_on", "boots"} <= {c["key"] for c in checklist_for(niche, "bundle")}


def test_full_inventory_lifecycle(db, niche, notifier):
    deals = load_seed_listings(db, niche, notify=False)
    deal = next(d for d in deals if d.should_alert and not d.item.is_bundle)
    from app.analytics.pnl import cash_available
    cash0 = cash_available(db)
    inv = mark_bought(db, deal, actual_price=deal.buy_price - 2)
    assert inv.cost_basis == round(deal.buy_price - 2 + deal.buyer_fees + deal.inbound_cost, 2)
    assert deal.status == "bought" and cash_available(db) == round(cash0 - inv.cost_basis, 2)
    set_status(db, inv, "testing")
    tr = record_test(db, inv, {"boots": "pass", "saves": "fail"})
    assert not tr.passed and inv.status == "ready_to_photograph"
    tr = record_test(db, inv, {"boots": "pass", "saves": "pass", "label_auth": "pass", "pcb_auth": "na", "disc_grade": "na", "region": "pass", "contents": "na"})
    assert tr.passed
    listing = generate_listing(db, inv)
    assert len(listing.title) <= 80 and listing.price > 0 and listing.markdown_schedule and listing.photo_shot_list
    assert "Tested" in listing.title or "Tested" in listing.description
    pl = list_on_ebay(db, listing)
    assert pl.external_id.startswith("mock-offer") and inv.status == "listed" and inv.listed_at
    add_platform_listing(db, listing, "vinted", "v123", "https://vinted/x")
    assert len(label_pdf([inv])) > 500 and listings_csv([listing]).count("\n") == 2
    sale = record_sale(db, inv, "vinted", 70.0, 0.0, postage_cost=3.35, packaging_cost=0.9)
    assert inv.status == "sold" and sale.net_profit == round(70 - inv.cost_basis - 3.35 - 0.9, 2)
    statuses = {p.platform: p.status for l in inv.listings for p in l.platform_listings}
    assert statuses == {"ebay": "ended", "vinted": "sold"}  # eBay ended automatically via API
    assert cash_available(db) == round(cash0 - inv.cost_basis + 70 - 3.35 - 0.9, 2)


def test_sale_on_ebay_flags_manual_removal_task(db, niche, notifier):
    deals = load_seed_listings(db, niche, notify=False)
    inv = mark_bought(db, next(d for d in deals if d.should_alert))
    listing = generate_listing(db, inv)
    list_on_ebay(db, listing)
    add_platform_listing(db, listing, "depop", "d1")
    record_sale(db, inv, "ebay", 60.0, 8.0)
    task = db.query(Task).filter(Task.kind == "remove_listings").one()
    assert task.urgent and "depop" in task.title and any("URGENT" in n.title for n in notifier.sent)
    pl = next(p for l in inv.listings for p in l.platform_listings if p.platform == "depop")
    assert pl.status == "remove_pending"
    mark_platform_removed(db, pl)
    assert task.done
