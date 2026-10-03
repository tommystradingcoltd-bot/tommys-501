"""APScheduler jobs: one per source, digest every 30 min, 8am daily summary, weekly insights, daily purge,
eBay sales sync, expire stale deals. Single-threaded executor keeps the browser helper sequential."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.config import get_settings
from app.db import db_session
from app.models import Deal, Source

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def run_source_job(slug: str) -> dict:
    from app.notify.service import notify_source_status
    from app.pipeline import process_listing
    from app.sourcing.runner import run_source
    with db_session() as db:
        src = db.scalar(select(Source).where(Source.slug == slug))
        if not src or not src.enabled:
            return {"skipped": "disabled"}
        before = src.status
        stats = run_source(db, src, process=process_listing)
        if src.status in ("needs_login", "blocked", "paused") and src.status != before:
            notify_source_status(db, src)
        log.info("source %s: %s", slug, stats)
        return stats


def digest_job() -> None:
    from app.notify.service import send_digest
    with db_session() as db:
        n = send_digest(db)
        if n:
            log.info("digest sent with %s alerts", n)


def daily_summary_job() -> None:
    from app.notify.service import send_daily_summary
    with db_session() as db:
        send_daily_summary(db)


def insights_job() -> None:
    from app.analytics.insights import generate_weekly_insights
    with db_session() as db:
        generate_weekly_insights(db)


def purge_job() -> None:
    from app.pipeline import purge_personal_data
    with db_session() as db:
        n = purge_personal_data(db, get_settings().passed_deal_retention_days)
        if n:
            log.info("purged personal data from %s old listings", n)


def expire_deals_job() -> None:
    """Auctions that ended / listings not seen for 3 days drop out of the open feed."""
    with db_session() as db:
        now = datetime.utcnow()
        for d in db.scalars(select(Deal).where(Deal.status.in_(["new", "alerted"]))):
            rl = d.raw_listing
            if (rl.ends_at and rl.ends_at < now) or rl.last_seen_at < now - timedelta(days=3):
                d.status = "expired"


def ebay_sales_sync_job() -> None:
    from app.inventory.service import sync_ebay_sales
    if get_settings().ebay_is_mock:
        return
    with db_session() as db:
        n = sync_ebay_sales(db, datetime.utcnow() - timedelta(days=2))
        if n:
            log.info("synced %s eBay sales", n)


def start_scheduler() -> Optional[BackgroundScheduler]:
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled or _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone=s.tz, executors={"default": ThreadPoolExecutor(1)},
                                job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    sched.add_job(digest_job, IntervalTrigger(minutes=s.digest_interval_min), id="digest", name="Alert digest")
    sched.add_job(daily_summary_job, CronTrigger(hour=s.daily_summary_hour, minute=0), id="daily", name="Daily summary")
    sched.add_job(insights_job, CronTrigger(day_of_week="mon", hour=7, minute=30), id="insights", name="Weekly insights")
    sched.add_job(purge_job, CronTrigger(hour=3, minute=15), id="purge", name="Personal-data purge")
    sched.add_job(expire_deals_job, IntervalTrigger(hours=1), id="expire", name="Expire stale deals")
    sched.add_job(ebay_sales_sync_job, IntervalTrigger(minutes=30), id="ebay_sales", name="eBay sales sync")
    sched.start()
    _scheduler = sched
    reschedule_sources()
    return sched


def reschedule_sources() -> None:
    if _scheduler is None:
        return
    s = get_settings()
    with db_session() as db:
        sources = db.scalars(select(Source)).all()
        for src in sources:
            job_id = f"source:{src.slug}"
            if _scheduler.get_job(job_id):
                _scheduler.remove_job(job_id)
            if not src.enabled:
                continue
            if src.kind == "browser" and not (s.browser_sources_enabled or s.mock_mode):
                continue
            minutes = max(1, src.poll_interval_min or s.source_poll_interval_min)
            _scheduler.add_job(run_source_job, IntervalTrigger(minutes=minutes, start_date=datetime.now() + timedelta(seconds=20 + 10 * src.id)),
                               args=[src.slug], id=job_id, name=f"Poll {src.name}")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def job_summary() -> list[dict]:
    if _scheduler is None:
        return []
    return [{"id": j.id, "name": j.name, "next_run": j.next_run_time.strftime("%d %b %H:%M") if j.next_run_time else "-"} for j in _scheduler.get_jobs()]
