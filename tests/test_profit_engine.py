from app.profit.engine import DealInput, FeeTable, calculate, fee_table_from_config, weight_class_for
from app.settings_store import DEFAULT_FEES

FEES = {k: v for k, _g, _l, v, _u, _n in DEFAULT_FEES}


def test_basic_pnl_adds_up():
    p = calculate(DealInput(buy_price=20, expected_sale_price=60, inbound_postage=2.5, outbound_postage=3.35),
                  FeeTable(sell_fee_pct=0.128, sell_fee_fixed=0.30, sell_regulatory_pct=0.0, packaging=0.9, reserve_pct=0.05))
    assert p.landed_cost == 22.5
    assert p.sell_fees == round(60 * 0.128 + 0.30, 2)
    assert p.net_profit == round(60 - 22.5 - (p.sell_fees + 3.35 + 0.9 + 3.0), 2)
    assert abs(p.net_margin - p.net_profit / 60) < 1e-4
    assert abs(p.roi - p.net_profit / 22.5) < 1e-4


def test_buyer_protection_fees_on_buy_side():
    p = calculate(DealInput(buy_price=100, expected_sale_price=200, inbound_postage=0), FeeTable(buy_fee_pct=0.05, buy_fee_fixed=0.70))
    assert p.buyer_fees == 5.70
    assert p.landed_cost == 105.70


def test_unknown_inbound_postage_is_estimated():
    p = calculate(DealInput(buy_price=10, expected_sale_price=30, inbound_postage=None, outbound_postage=3.35), FeeTable())
    assert p.inbound_cost == 3.35
    assert any("inbound postage unknown" in n for n in p.notes)


def test_collection_distance_cost():
    near = calculate(DealInput(buy_price=40, expected_sale_price=100, collection_only=True, distance_miles=5), FeeTable())
    far = calculate(DealInput(buy_price=40, expected_sale_price=100, collection_only=True, distance_miles=120), FeeTable())
    assert near.collection_cost > 0
    assert far.collection_cost > near.collection_cost
    # 120 miles each way at 45p + 8h drive at £12 + 20 min handling
    assert far.collection_cost == round(240 * 0.45 + (240 / 30 + 20 / 60) * 12, 2)
    assert far.net_profit < 0


def test_collection_unknown_distance_has_zero_inbound_and_note():
    p = calculate(DealInput(buy_price=40, expected_sale_price=100, collection_only=True, distance_miles=None), FeeTable())
    assert p.inbound_cost == 0
    assert any("distance unknown" in n for n in p.notes)


def test_bundle_multiplies_per_item_costs():
    one = calculate(DealInput(buy_price=50, expected_sale_price=150, inbound_postage=5, outbound_postage=1.55, bundle_item_count=1), FeeTable(packaging=0.4))
    five = calculate(DealInput(buy_price=50, expected_sale_price=150, inbound_postage=5, outbound_postage=1.55, bundle_item_count=5), FeeTable(packaging=0.4))
    assert five.outbound_postage == round(1.55 * 5, 2)
    assert five.packaging == 2.0
    assert five.sell_fees == round(one.sell_fees + FeeTable().sell_fee_fixed * 4, 2)
    assert five.net_profit < one.net_profit


def test_listing_uplift_raises_sale_price():
    base = calculate(DealInput(buy_price=10, expected_sale_price=50, inbound_postage=0), FeeTable())
    up = calculate(DealInput(buy_price=10, expected_sale_price=50, inbound_postage=0, listing_uplift=0.10), FeeTable())
    assert up.expected_sale_price == 55.0
    assert up.net_profit > base.net_profit


def test_zero_sale_price_is_total_loss():
    p = calculate(DealInput(buy_price=10, expected_sale_price=0, inbound_postage=2), FeeTable())
    assert p.net_margin == -1.0
    assert p.net_profit < 0


def test_fee_table_from_config_uses_source_specific_buyer_fees():
    vinted = fee_table_from_config(FEES, "vinted", "ebay", "large_letter")
    ebay = fee_table_from_config(FEES, "ebay", "ebay", "small_parcel")
    fb = fee_table_from_config(FEES, "facebook", "ebay", "medium_parcel")
    assert vinted.buy_fee_pct == 0.05 and vinted.buy_fee_fixed == 0.70
    assert ebay.buy_fee_pct == 0.04 and ebay.sell_fee_pct == 0.128
    assert fb.buy_fee_pct == 0.0
    assert vinted.packaging == 0.40 and ebay.packaging == 0.90 and fb.packaging == 1.80
    assert ebay.payment_pct == 0.0  # eBay managed payments included in FVF


def test_weight_class_mapping():
    cfg = {"postage_classes": {"game_loose": "large_letter", "game_boxed": "small_parcel", "console": "medium_parcel", "bundle": "medium_parcel", "accessory": "small_parcel"}}
    assert weight_class_for(cfg, "game", "loose", False) == "large_letter"
    assert weight_class_for(cfg, "game", "cib", False) == "small_parcel"
    assert weight_class_for(cfg, "console", "boxed", False) == "medium_parcel"
    assert weight_class_for(cfg, "game", "loose", True) == "medium_parcel"
