
from app.notify.service import format_deal, queue_deal_alert, send_daily_summary, send_digest, notify_source_status
from app.pipeline import load_seed_listings
from app.models import Alert, Source


def test_format_and_digest_flow(db, niche, notifier):
    from app.settings_store import set_setting
    set_setting(db, "notify_quiet_hours", "")
    deals = load_seed_listings(db, niche, notify=False)
    alerted = [d for d in deals if d.should_alert]
    assert alerted
    n = format_deal(alerted[0])
    for needle in ("buy £", "net £", "margin", "days to sell", "score", "Risk:", "Listing: http", alerted[0].raw_listing.source.name):
        assert needle in n.body or needle in n.title
    assert n.url == f"http://test/deals/{alerted[0].id}"
    assert len(n.actions) == 2
    for d in alerted:
        queue_deal_alert(db, d, notifier)
    high = [d for d in alerted if d.priority == "high"]
    assert len(notifier.sent) == len(high)
    pending = db.query(Alert).filter(Alert.status == "pending").count()
    assert pending == len(alerted) - len(high)
    n_digested = send_digest(db, notifier)
    assert n_digested == pending
    assert notifier.sent[-1].title.endswith("(digest)") and notifier.sent[-1].priority == "low"
    assert send_digest(db, notifier) == 0


def test_collection_deal_shows_distance(db, niche, notifier):
    deals = load_seed_listings(db, niche, notify=False)
    coll = next(d for d in deals if d.collection_only and d.distance_miles is not None)
    assert "mi each way" in format_deal(coll).body


def test_daily_summary_and_source_notice(db, niche, notifier):
    a = send_daily_summary(db, notifier)
    assert a.status == "sent" and "Cash available" in a.body
    src = db.query(Source).filter_by(slug="vinted").one()
    src.status, src.status_message = "needs_login", "login wall"
    notify_source_status(db, src, notifier)
    notify_source_status(db, src, notifier)  # de-duplicated within 6h
    assert sum(1 for n in notifier.sent if "Vinted needs you to log in" in n.body) == 1


def test_quiet_hours_hold_high_priority(db, niche, notifier, monkeypatch):
    from app.settings_store import set_setting
    import app.notify.service as svc
    set_setting(db, "notify_quiet_hours", "00-23")
    monkeypatch.setattr(svc, "in_quiet", lambda now, quiet: True)
    deals = load_seed_listings(db, niche, notify=False)
    d = next(x for x in deals if x.should_alert)
    d.priority = "high"
    a = queue_deal_alert(db, d, notifier)
    assert a.status == "pending" and not notifier.sent
