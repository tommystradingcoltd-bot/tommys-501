"""De-duplication: exact (source + external id) and fuzzy cross-post detection."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RawListing

TITLE_SIMILARITY = 90      # rapidfuzz token_set_ratio threshold
PRICE_TOLERANCE = 0.05     # +/- 5%
HASH_DISTANCE = 6          # perceptual hash hamming distance


def hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 99
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def is_cross_post(a_title: str, a_price: float, a_hash: str, b_title: str, b_price: float, b_hash: str) -> bool:
    """Same item posted on another site? Needs similar title + price; image hash confirms when present."""
    if a_price <= 0 or b_price <= 0:
        return False
    price_close = abs(a_price - b_price) / max(a_price, b_price) <= PRICE_TOLERANCE
    title_sim = fuzz.token_set_ratio(a_title.lower(), b_title.lower())
    if a_hash and b_hash:
        if hamming(a_hash, b_hash) <= HASH_DISTANCE and title_sim >= 70:
            return True
    return price_close and title_sim >= TITLE_SIMILARITY


def find_duplicate(db: Session, listing: RawListing, window_days: int = 14) -> Optional[RawListing]:
    """Find an earlier listing (any source) that looks like the same item."""
    since = datetime.utcnow() - timedelta(days=window_days)
    lo, hi = listing.price * (1 - PRICE_TOLERANCE), listing.price * (1 + PRICE_TOLERANCE)
    candidates = db.scalars(
        select(RawListing).where(
            RawListing.id != listing.id,
            RawListing.first_seen_at >= since,
            RawListing.status != "duplicate",
            RawListing.price >= lo * 0.5, RawListing.price <= hi * 1.5,
        ).order_by(RawListing.first_seen_at)
    ).all()
    for c in candidates:
        if c.id is not None and listing.id is not None and c.id >= listing.id:
            continue
        if is_cross_post(listing.title, listing.price, listing.image_hash, c.title, c.price, c.image_hash):
            return c
    return None
