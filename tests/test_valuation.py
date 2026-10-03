from datetime import datetime, timedelta

from app.identification.valuation import (Comp, CsvImportProvider, MockSoldProvider, OwnSalesProvider, compute_valuation,
                                          estimate_days_to_sell, seed_mock_comps, value_bundle, value_item)
from app.models import Valuation


def comps(prices, provider="mock"):
    return [Comp(price=p, sold_at=datetime.utcnow(), provider=provider) for p in prices]


def test_compute_valuation_stats_and_confidence():
    v = compute_valuation(comps([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]), active_count=10)
    assert v.median == 50 and v.p25 == 30 and v.p75 == 80
    assert v.sold_count == 10 and v.confidence == "medium"
    assert compute_valuation(comps([10, 12, 11]), 5).confidence == "low"
    assert compute_valuation(comps([20] * 20), 5).confidence == "high"
    assert compute_valuation([], 5).confidence == "low" and compute_valuation([], 5).est_days == 365


def test_days_to_sell_model():
    assert estimate_days_to_sell(0, 10, 90) == 365
    fast = estimate_days_to_sell(60, 10, 90)
    slow = estimate_days_to_sell(5, 40, 90)
    assert 3 <= fast < slow <= 365


def test_weighted_comps_shift_median():
    heavy = [Comp(100, datetime.utcnow(), weight=4.0, provider="own_sales")] + comps([50, 50, 50])
    assert compute_valuation(heavy, 1).median == 100


def test_value_item_caches(db, niche):
    seed_mock_comps(db, niche)
    v1 = value_item(db, niche, "SNES", "Super Metroid", "PAL", "loose", [MockSoldProvider()])
    v2 = value_item(db, niche, "SNES", "Super Metroid", "PAL", "loose", [MockSoldProvider()])
    assert v1.id == v2.id and v1.sold_count >= 15 and 40 < v1.median_price < 70
    assert db.query(Valuation).count() == 1
    v3 = value_item(db, niche, "SNES", "Super Metroid", "PAL", "loose", [MockSoldProvider()], use_cache=False)
    assert v3.id != v1.id


def test_value_item_falls_back_across_completeness(db, niche):
    seed_mock_comps(db, niche)
    v = value_item(db, niche, "GameCube", "Mario Kart Double Dash", "PAL", "loose", [MockSoldProvider()])
    assert v.sold_count > 0 and v.median_price < 45  # loose adjusted down from cib comps


def test_value_bundle_sums_parts(db, niche):
    seed_mock_comps(db, niche)
    total, days, conf, parts = value_bundle(db, niche, [{"platform": "N64", "title": "Mario Kart 64", "completeness": "loose"},
                                                        {"platform": "N64", "title": "GoldenEye 007", "completeness": "loose"}], [MockSoldProvider()])
    assert len(parts) == 2 and abs(total - sum(p["median"] for p in parts)) < 0.01 and conf == "high"


def test_csv_import_and_provider(db, niche):
    csv = "Title,Sold Price,Date Sold,Platform,Completeness\nSuper Metroid SNES,£55.00,01/09/2026,SNES,loose\nSuper Metroid,52,2026-09-10,SNES,loose\nbad row,,\n"
    assert CsvImportProvider.import_csv(db, niche, csv) == 2
    assert CsvImportProvider.import_csv(db, niche, csv) == 0  # idempotent
    got = CsvImportProvider().fetch_comps(db, niche, "SNES", "Super Metroid", "PAL", "loose", datetime.utcnow() - timedelta(days=90))
    assert len(got) == 2


def test_own_sales_provider_weights_grow(db, niche):
    from app.models import InventoryItem, Sale
    for i in range(3):
        inv = InventoryItem(sku=f"T-{i}", niche_id=niche.id, title="Super Metroid", platform="SNES", completeness="loose", cost_basis=20)
        db.add(inv)
        db.flush()
        db.add(Sale(inventory_item_id=inv.id, platform="ebay", sale_price=60 + i, sold_at=datetime.utcnow()))
    db.flush()
    got = OwnSalesProvider().fetch_comps(db, niche, "SNES", "Super Metroid", "PAL", "loose", datetime.utcnow() - timedelta(days=90))
    assert len(got) == 3 and got[0].weight == 1.75
