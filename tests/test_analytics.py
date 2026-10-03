from app.analytics.insights import clone_ready, rule_based_insights, generate_weekly_insights
from app.analytics.projections import ProjectionInputs, project


def test_projection_ranges_ordered_and_capped():
    p = project(ProjectionInputs(current_capital=5000, net_margin=0.3, avg_days_to_sell=20, monthly_buying_capacity=4000))
    for i in range(3):
        assert p["worst"][i]["capital"] <= p["expected"][i]["capital"] <= p["best"][i]["capital"]
    assert p["expected"][0]["month"] == 3 and p["expected"][2]["month"] == 12
    assert p["expected"][2]["capital"] < 200_000   # capacity cap keeps it sane


def test_clone_rule():
    rule = {"months": 3, "min_margin": 0.3, "max_avg_days": 30}
    good = [{"month": m, "sales": 5, "margin": 0.35, "avg_days": 20} for m in ("2026-07", "2026-08", "2026-09")]
    assert clone_ready(good, rule)[0]
    bad = good[:2] + [{"month": "2026-09", "sales": 5, "margin": 0.2, "avg_days": 20}]
    ok, why = clone_ready(bad, rule)
    assert not ok and "2026-09" in why
    assert not clone_ready(good[:2], rule)[0]


def test_weekly_insights_generation(db, niche):
    row = generate_weekly_insights(db)
    assert "selling fastest" in row.content_md and not row.ready_to_clone
    assert rule_based_insights({"clone_reason": "x"}).count("##") >= 6
