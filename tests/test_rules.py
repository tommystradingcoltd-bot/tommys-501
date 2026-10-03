from app.profit.rules import RuleConfig, evaluate, score_deal, tier_for


def ev(**kw):
    base = dict(net_profit=20, net_margin=0.35, est_days=10, confidence="high", buy_price=30, landed_cost=33, cash_available=4000, cfg=RuleConfig())
    base.update(kw)
    return evaluate(**base)


def test_tiers():
    cfg = RuleConfig()
    assert tier_for(0, cfg) == ("0-14d", 0.25)
    assert tier_for(14, cfg) == ("0-14d", 0.25)
    assert tier_for(15, cfg) == ("15-30d", 0.30)
    assert tier_for(45, cfg) == ("31-60d", 0.40)
    assert tier_for(61, cfg) == ("61d+", None)


def test_tier_thresholds_apply():
    assert ev(net_margin=0.26, est_days=10).should_alert
    assert not ev(net_margin=0.24, est_days=10).should_alert
    assert ev(net_margin=0.31, est_days=20).should_alert
    assert not ev(net_margin=0.29, est_days=20).should_alert


def test_over_60_days_never_alerts():
    d = ev(net_margin=0.9, est_days=61)
    assert not d.should_alert and "beyond" in d.reason


def test_min_profit_floor():
    d = ev(net_profit=7.99, net_margin=0.5)
    assert not d.should_alert and "floor" in d.reason
    assert ev(net_profit=8.0, net_margin=0.5).should_alert


def test_large_deal_relief():
    # 15-30d tier needs 30%; large deals (> £150) get 5 points off
    assert not ev(net_margin=0.27, est_days=20, buy_price=100).should_alert
    assert ev(net_margin=0.27, est_days=20, buy_price=200, net_profit=60).should_alert
    assert not ev(net_margin=0.24, est_days=20, buy_price=200, net_profit=60).should_alert


def test_phase_mode_capital_growth_blocks_slow_tiers_unless_50pct():
    cg = RuleConfig(phase_mode="capital_growth")
    steady = RuleConfig(phase_mode="steady")
    assert not ev(net_margin=0.45, est_days=45, cfg=cg).should_alert
    assert ev(net_margin=0.55, est_days=45, cfg=cg).should_alert
    assert ev(net_margin=0.45, est_days=45, cfg=steady).should_alert
    assert ev(net_margin=0.31, est_days=20, cfg=cg).should_alert  # fast tiers unaffected


def test_low_confidence_needs_60_and_is_flagged_check_manually():
    assert not ev(net_margin=0.5, confidence="low").should_alert
    d = ev(net_margin=0.65, confidence="low", net_profit=40)
    assert d.should_alert and d.check_manually and "check manually" in d.reason


def test_capital_warning():
    d = ev(cash_available=320, landed_cost=33)
    assert d.capital_warning
    assert not ev(cash_available=400, landed_cost=33).capital_warning
    assert not ev(cash_available=None).capital_warning


def test_score_prefers_margin_speed_confidence_and_size():
    assert score_deal(0.5, 7, "high", 40) > score_deal(0.3, 7, "high", 40)
    assert score_deal(0.5, 7, "high", 40) > score_deal(0.5, 40, "high", 40)
    assert score_deal(0.5, 7, "high", 40) > score_deal(0.5, 7, "low", 40)
    assert score_deal(0.5, 7, "high", 40) > score_deal(0.5, 7, "high", 9)
    assert 0 <= score_deal(0.9, 3, "high", 500) <= 100


def test_high_priority_from_score():
    d = ev(net_margin=0.6, est_days=5, net_profit=80)
    assert d.priority == "high"
    assert ev(net_margin=0.26, est_days=12, net_profit=9).priority == "default"
