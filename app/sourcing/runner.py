"""Run one source: search all active queries, persist new listings, de-dupe, hand off to the pipeline."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Niche, RawListing as RawListingRow, Source
from app.sourcing.base import RawListing, SourceError, SourcePaused
from app.sourcing.dedupe import find_duplicate
from app.sourcing.registry import build_watcher

log = logging.getLogger(__name__)


def persist_listing(db: Session, source: Source, niche: Niche, rl: RawListing) -> tuple[RawListingRow, bool]:
    """Insert or touch a raw listing. Returns (row, is_new)."""
    row = db.scalar(select(RawListingRow).where(RawListingRow.source_id == source.id, RawListingRow.external_id == rl.external_id))
    if row:
        row.last_seen_at = datetime.utcnow()
        if rl.price and rl.price != row.price:
            row.price = rl.price
        return row, False
    row = RawListingRow(
        source_id=source.id, niche_id=niche.id, external_id=rl.external_id, url=rl.url, title=rl.title,
        description=rl.description, price=rl.price, currency=rl.currency, listing_type=rl.listing_type,
        ends_at=rl.ends_at, postage_cost=rl.postage_cost, collection_only=rl.collection_only,
        location_text=rl.location_text, postcode_district=rl.postcode_district, seller_name=rl.seller_name,
        seller_feedback=rl.seller_feedback, image_urls=rl.image_urls, condition_text=rl.condition_text, raw=rl.raw,
        image_hash=rl.raw.get("image_hash", ""),
    )
    db.add(row)
    db.flush()
    dup = find_duplicate(db, row)
    if dup:
        row.status = "duplicate"
        row.duplicate_of_id = dup.id
    return row, True


def run_source(db: Session, source: Source, niches: list[Niche] | None = None, watcher=None, process=None,
               max_queries: int | None = None) -> dict:
    """Poll one source. `process(db, row)` is called for each new listing (the pipeline). Returns stats."""
    stats = {"source": source.slug, "queries": 0, "found": 0, "new": 0, "duplicates": 0, "errors": 0}
    if not source.enabled:
        return stats
    if source.status in ("needs_login", "blocked"):
        stats["skipped"] = source.status
        return stats
    watcher = watcher or build_watcher(source.slug, source.config)
    if watcher is None:
        source.status = "disabled"
        source.status_message = "no watcher available (browser sources need BROWSER_SOURCES_ENABLED=true and a logged-in profile)"
        return stats
    niches = niches or db.scalars(select(Niche).where(Niche.active == True)).all()  # noqa: E712
    source.last_run_at = datetime.utcnow()
    queries = []
    for niche in niches:
        for q in niche.search_queries:
            if q.active and (q.source_id is None or q.source_id == source.id):
                queries.append((niche, q))
    if max_queries:
        queries = queries[:max_queries]
    for niche, q in queries:
        stats["queries"] += 1
        try:
            results = _with_retry(lambda: watcher.search(q.query, q.filters or {}))
        except SourcePaused as p:
            source.status = p.status
            source.status_message = p.message
            log.warning("source %s paused: %s", source.slug, p.message)
            stats["paused"] = p.message
            break
        except SourceError as e:
            stats["errors"] += 1
            source.last_error = str(e)[:500]
            log.warning("source %s query %r failed: %s", source.slug, q.query, e)
            continue
        q.last_run_at = datetime.utcnow()
        for rl in results:
            stats["found"] += 1
            row, is_new = persist_listing(db, source, niche, rl)
            if not is_new:
                continue
            stats["new"] += 1
            if row.status == "duplicate":
                stats["duplicates"] += 1
                continue
            if process:
                try:
                    process(db, row)
                except Exception:  # pragma: no cover - defensive; pipeline logs its own errors
                    log.exception("pipeline failed for listing %s", row.id)
                    row.status = "error"
        db.flush()
    if "paused" not in stats:
        source.status = "ok" if stats["errors"] == 0 else "error"
        source.status_message = "" if stats["errors"] == 0 else source.last_error
        source.last_success_at = datetime.utcnow()
    return stats


def _with_retry(fn, attempts: int = 3, base: float = 1.0):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except SourceError as e:
            last = e
            if i < attempts - 1:
                time.sleep(base * (2 ** i))
    assert last is not None
    raise last
