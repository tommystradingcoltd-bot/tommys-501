"""Alert dispatch: format deal alerts, send high-priority ones immediately, batch the rest into digests,
send a daily 8am summary and source-status notifications. All alerts are recorded in the alerts table."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, Deal, InventoryItem, Sale, Source
from app.notify.base import Notification, Notifier
from app.notify.mock import MockNotifier
from app.settings_store import get_setting

log = logging.getLogger(__name__)
_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        s = get_settings()
        if s.notifier == "ntfy" and not s.mock_mode:
            from app.notify.ntfy import NtfyNotifier
            _notifier = NtfyNotifier(s.ntfy_server, s.ntfy_topic, s.ntfy_token)
        elif s.notifier == "pushover" and not s.mock_mode:
            from app.notify.pushover import PushoverNotifier
            _notifier = PushoverNotifier(s.pushover_user_key, s.pushover_app_token)
        else:
            _notifier = MockNotifier()
    return _notifier


def set_notifier(n: Notifier | None) -> None:
    global _notifier
    _notifier = n


def deal_url(deal_id: int) -> str:
    return f"{get_settings().dashboard_base_url.rstrip('/')}/deals/{deal_id}"


def format_deal(deal: Deal) -> Notification:
    item, listing = deal.item, deal.raw_listing
    flags = ", ".join(f["label"] for f in (item.risk_flags or [])[:4]) or "none"
    name = f"{item.platform} {item.title}" if item.title != "bundle" else f"{item.platform} bundle ({len(item.bundle_items)} items)"
    if item.completeness and item.completeness != "unknown" and item.title != "bundle":
        name += f" ({item.completeness})"
    lines = [
        f"{listing.source.name}: buy £{deal.buy_price:.2f}" + (" (auction)" if listing.listing_type == "auction" else ""),
        f"Sell ~£{deal.expected_sale_price:.2f} -> net £{deal.net_profit:.2f} ({deal.net_margin:.0%} margin, ROI {deal.roi:.0%})",
        f"Est. {deal.est_days_to_sell} days to sell | score {deal.score:.0f} | tier {deal.tier}",
        f"Risk: {flags}",
    ]
    if deal.collection_only:
        dist = f"{deal.distance_miles:.0f} mi each way" if deal.distance_miles is not None else "distance unknown"
        lines.append(f"Collection only ({listing.location_text or listing.postcode_district or '?'}): {dist}, trip cost £{deal.inbound_cost:.2f}")
    if deal.check_manually:
        lines.append("CHECK MANUALLY: low-confidence valuation")
    if deal.capital_warning:
        lines.append("WARNING: buying would take cash below your reserve")
    if listing.ends_at:
        lines.append(f"Ends {listing.ends_at:%a %H:%M}")
    lines.append(f"Listing: {listing.url}")
    title = f"{'HOT ' if deal.priority == 'high' else ''}£{deal.net_profit:.0f} / {deal.net_margin:.0%} - {name}"[:120]
    tags = ["moneybag"] if deal.priority == "high" else ["mag"]
    if deal.check_manually:
        tags.append("warning")
    return Notification(title=title, body="\n".join(lines), priority=deal.priority, url=deal_url(deal.id),
                        actions=[{"label": "Listing", "url": listing.url}, {"label": "Deal", "url": deal_url(deal.id)}], tags=tags)


def in_quiet(now: datetime | None, quiet: str) -> bool:
    from app.sourcing.browser.helper import in_quiet_hours
    return in_quiet_hours(quiet, now)


def queue_deal_alert(db: Session, deal: Deal, notifier: Notifier | None = None) -> Alert:
    """High-priority: send now (unless quiet hours). Others: queue for the next digest."""
    notifier = notifier or get_notifier()
    n = format_deal(deal)
    alert = Alert(deal_id=deal.id, kind="deal", channel=notifier.name, priority=deal.priority, title=n.title, body=n.body, url=n.url)
    db.add(alert)
    quiet = get_setting(db, "notify_quiet_hours", "22-07")
    if deal.priority == "high" and not in_quiet(datetime.now(), quiet):
        _send(alert, n, notifier)
    deal.status = "alerted"
    db.flush()
    return alert


def _send(alert: Alert, n: Notification, notifier: Notifier) -> None:
    ok = False
    try:
        ok = notifier.send(n)
    except Exception as e:  # pragma: no cover
        alert.error = str(e)[:500]
    alert.status = "sent" if ok else "failed"
    alert.sent_at = datetime.utcnow() if ok else None


def send_digest(db: Session, notifier: Notifier | None = None) -> int:
    """Batch all pending deal alerts into one message. Returns the number digested."""
    notifier = notifier or get_notifier()
    pending = db.scalars(select(Alert).where(Alert.kind == "deal", Alert.status == "pending").order_by(Alert.created_at)).all()
    if not pending:
        return 0
    quiet = get_setting(db, "notify_quiet_hours", "22-07")
    if in_quiet(datetime.now(), quiet):
        return 0
    deals = [a.deal for a in pending if a.deal is not None]
    deals.sort(key=lambda d: -d.score)
    lines = []
    for d in deals[:12]:
        name = f"{d.item.platform} {d.item.title}"[:40]
        lines.append(f"£{d.net_profit:.0f} ({d.net_margin:.0%}, {d.est_days_to_sell}d) {name} - {d.raw_listing.source.name} £{d.buy_price:.0f}" + (" [check]" if d.check_manually else ""))
    if len(deals) > 12:
        lines.append(f"...and {len(deals) - 12} more in the dashboard")
    n = Notification(title=f"{len(deals)} new deals (digest)", body="\n".join(lines), priority="low",
                     url=f"{get_settings().dashboard_base_url.rstrip('/')}/deals", tags=["newspaper"])
    digest = Alert(kind="digest", channel=notifier.name, priority="low", title=n.title, body=n.body, url=n.url)
    db.add(digest)
    _send(digest, n, notifier)
    for a in pending:
        a.status = "digested"
        a.sent_at = datetime.utcnow()
    db.flush()
    return len(pending)


def send_daily_summary(db: Session, notifier: Notifier | None = None) -> Alert:
    from app.analytics.pnl import cash_available, stock_value_at_cost
    notifier = notifier or get_notifier()
    since = datetime.utcnow() - timedelta(days=1)
    new_deals = db.scalar(select(func.count(Deal.id)).where(Deal.created_at >= since)) or 0
    alerted = db.scalar(select(func.count(Deal.id)).where(Deal.created_at >= since, Deal.should_alert == True)) or 0  # noqa: E712
    sold = db.scalars(select(Sale).where(Sale.sold_at >= since)).all()
    overdue = [i for i in db.scalars(select(InventoryItem).where(InventoryItem.status == "listed")) if i.is_overdue]
    month_start = date.today().replace(day=1)
    month_profit = db.scalar(select(func.coalesce(func.sum(Sale.net_profit), 0.0)).where(Sale.sold_at >= datetime.combine(month_start, datetime.min.time()))) or 0.0
    paused = db.scalars(select(Source).where(Source.enabled == True, Source.status.in_(["needs_login", "blocked", "paused"]))).all()  # noqa: E712
    lines = [
        f"Yesterday: {new_deals} listings scored, {alerted} worth alerting, {len(sold)} sales (£{sum(s.net_profit for s in sold):.0f} net)",
        f"Month so far: £{month_profit:.0f} realised profit",
        f"Cash available £{cash_available(db):.0f} | stock at cost £{stock_value_at_cost(db):.0f}",
    ]
    if overdue:
        lines.append(f"{len(overdue)} listed items past their expected sell date - consider a markdown")
    if paused:
        lines.append("Sources needing attention: " + ", ".join(f"{s.name} ({s.status.replace('_', ' ')})" for s in paused))
    n = Notification(title="DealFinder daily summary", body="\n".join(lines), priority="low",
                     url=get_settings().dashboard_base_url, tags=["sunrise"])
    alert = Alert(kind="daily", channel=notifier.name, priority="low", title=n.title, body=n.body, url=n.url)
    db.add(alert)
    _send(alert, n, notifier)
    db.flush()
    return alert


def notify_source_status(db: Session, source: Source, notifier: Notifier | None = None) -> None:
    """'Vinted needs you to log in / check the browser' style notification, at most once per status change."""
    notifier = notifier or get_notifier()
    recent = db.scalar(select(Alert).where(Alert.kind == "source", Alert.title.contains(source.name),
                                           Alert.created_at >= datetime.utcnow() - timedelta(hours=6)))
    if recent:
        return
    msg = {"needs_login": f"{source.name} needs you to log in / check the browser",
           "blocked": f"{source.name} is blocking requests - paused until you check it",
           "paused": f"{source.name} paused: {source.status_message}"}.get(source.status, f"{source.name}: {source.status_message}")
    n = Notification(title=f"Source paused: {source.name}", body=msg, priority="default",
                     url=f"{get_settings().dashboard_base_url.rstrip('/')}/health", tags=["pause_button"])
    alert = Alert(kind="source", channel=notifier.name, priority="default", title=n.title, body=n.body, url=n.url)
    db.add(alert)
    _send(alert, n, notifier)
    db.flush()


def notify_task(db: Session, title: str, body: str, url: str = "", notifier: Notifier | None = None) -> None:
    notifier = notifier or get_notifier()
    n = Notification(title=title, body=body, priority="high", url=url, tags=["rotating_light"])
    alert = Alert(kind="task", channel=notifier.name, priority="high", title=title, body=body, url=url)
    db.add(alert)
    _send(alert, n, notifier)
    db.flush()
