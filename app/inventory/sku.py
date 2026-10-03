"""SKU generator: <NICHE>-<PLATFORM>-<YYMM>-<SEQ>, e.g. RG-SNES-2610-0042."""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InventoryItem


def _abbr(text: str, n: int) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    if len(words) >= 2:
        s = "".join(w[0] for w in words)
    else:
        s = text
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return (s or "X")[:n]


def next_sku(db: Session, niche_slug: str, platform: str, today: date | None = None) -> str:
    today = today or date.today()
    prefix = f"{_abbr(niche_slug.replace('_', ' '), 3)}-{_abbr(platform or 'GEN', 5)}-{today:%y%m}-"
    count = db.scalar(select(func.count(InventoryItem.id)).where(InventoryItem.sku.like(prefix + "%"))) or 0
    while True:
        count += 1
        sku = f"{prefix}{count:04d}"
        if not db.scalar(select(InventoryItem.id).where(InventoryItem.sku == sku)):
            return sku
