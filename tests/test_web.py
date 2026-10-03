from sqlalchemy import select

from app.models import Deal, FeeConfig, Niche, Source
from app.pipeline import load_seed_listings


def test_pages_render(client, db, niche):
    load_seed_listings(db, niche)
    db.commit()
    for path in ["/", "/deals", "/deals?show_all=1&sort=distance&source=facebook", "/inventory", "/pnl", "/projections", "/insights",
                 "/health", "/settings", "/settings?tab=fees", "/settings?tab=postage", "/settings?tab=sources", "/niches", "/sold-data"]:
        r = client.get(path)
        assert r.status_code == 200, path
    assert client.get("/healthz").json()["sources"]["ebay"]["enabled"] is True


def test_deal_decisions_and_bought_creates_stock(client, db, niche):
    load_seed_listings(db, niche)
    db.commit()
    deal = db.scalar(select(Deal).where(Deal.should_alert == True))  # noqa: E712
    r = client.get(f"/deals/{deal.id}")
    assert r.status_code == 200 and b"Net profit" in r.content
    r = client.post(f"/deals/{deal.id}/decide", data={"action": "watch"}, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(Deal, deal.id).status == "watching"
    r = client.post(f"/deals/{deal.id}/decide", data={"action": "bought", "actual_price": "20"}, follow_redirects=False)
    assert r.headers["location"].startswith("/inventory/")
    item_url = r.headers["location"]
    assert client.get(item_url).status_code == 200
    assert client.get(item_url + "/label.pdf").headers["content-type"] == "application/pdf"
    r = client.post(item_url + "/listing", follow_redirects=False)
    assert r.status_code == 303
    assert b"Auto-markdown" in client.get(item_url).content


def test_settings_save(client, db):
    r = client.post("/settings/rules", data={"phase_mode": "steady", "min_net_profit": "10", "capital_reserve": "500", "large_deal_threshold": "200",
                                             "large_deal_margin_relief": "5", "low_confidence_min_margin": "60", "steady_min_margin_override": "50",
                                             "max_days_to_alert": "60", "tier_rules": '[{"max_days": 14, "min_margin": 0.2}]', "listing_quality_uplift": "2",
                                             "high_priority_score": "70", "collection_max_miles": "50", "monthly_buying_capacity": "3000", "starting_capital": "5000"},
                    follow_redirects=False)
    assert r.status_code == 303 and "Saved" in r.headers["location"]
    from app.settings_store import get_setting
    db.expire_all()
    assert get_setting(db, "phase_mode") == "steady" and get_setting(db, "tier_rules") == [{"max_days": 14, "min_margin": 0.2}]
    r = client.post("/settings/location", data={"postcode": "LS1", "label": "Leeds"}, follow_redirects=False)
    assert "Saved" in r.headers["location"]
    db.expire_all()
    assert get_setting(db, "base_location")["lat"] == 53.8
    fee = db.scalar(select(FeeConfig).where(FeeConfig.key == "ebay_fvf_pct"))
    client.post(f"/settings/fees/{fee.id}", data={"value": "13.0", "verified": "1"}, follow_redirects=False)
    db.expire_all()
    fee = db.get(FeeConfig, fee.id)
    assert fee.value == 13.0 and not fee.verify_flag
    src = db.scalar(select(Source).where(Source.slug == "vinted"))
    client.post(f"/settings/sources/{src.id}", data={"enabled": "1", "poll_interval_min": "20", "max_page_loads_per_hour": "30", "min_delay_s": "60",
                                                      "max_delay_s": "150", "quiet_hours": "22-08", "buyer_fee_pct": "5", "buyer_fee_fixed": "0.7"}, follow_redirects=False)
    db.expire_all()
    src = db.get(Source, src.id)
    assert src.enabled and src.max_page_loads_per_hour == 30 and src.quiet_hours == "22-08"


def test_create_niche_and_upload_sold_csv(client, db):
    r = client.post("/niches/new", data={"slug": "vintage lego", "name": "Vintage LEGO", "search_terms": "lego job lot\nlego technic"}, follow_redirects=False)
    assert r.status_code == 303 and "Created" in r.headers["location"]
    db.expire_all()
    n = db.scalar(select(Niche).where(Niche.slug == "vintage_lego"))
    assert n and len(n.search_queries) == 2
    assert client.get(f"/niches/{n.id}").status_code == 200
    r = client.post(f"/niches/{n.id}/config", data={"config_yaml": "name: Vintage LEGO\nsearch_terms:\n- lego star wars\n", "active": "1"}, follow_redirects=False)
    assert "Saved" in r.headers["location"]
    db.expire_all()
    assert len(db.get(Niche, n.id).search_queries) == 3
    r = client.post("/sold-data/upload", data={"niche_id": str(n.id), "default_platform": "SNES"},
                    files={"file": ("comps.csv", "title,sold_price,sold_at\nLego 8880,120,2026-09-01\n", "text/csv")}, follow_redirects=False)
    assert "Imported+1" in r.headers["location"]


def test_walkthrough_flag_and_routes(client, db):
    assert b'data-tour="on"' in client.get("/").content
    assert client.post("/walkthrough/done").json() == {"ok": True}
    assert b'data-tour="off"' in client.get("/").content
    r = client.post("/walkthrough/restart", follow_redirects=False)
    assert r.status_code == 303 and b'data-tour="on"' in client.get("/").content
    assert client.get("/static/tour.js").status_code == 200
