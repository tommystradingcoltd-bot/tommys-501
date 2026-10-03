"""Sold-price lookup and valuation.

SoldDataProvider implementations:
  * EbayMarketplaceInsightsProvider - official sold-items API (restricted; mocked until keys/approval exist)
  * CsvImportProvider              - Terapeak / Seller Hub CSV exports uploaded via the dashboard
  * OwnSalesProvider               - my own sales (Module 5), weighted more over time
  * MockSoldProvider               - seeded comps for demo/tests
No scraping of eBay sold pages anywhere.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Protocol

import httpx
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import InventoryItem, Niche, Sale, SoldComp, Valuation
from app.settings_store import get_setting

log = logging.getLogger(__name__)


@dataclass
class Comp:
    price: float
    sold_at: datetime
    weight: float = 1.0
    provider: str = ""
    title: str = ""


class SoldDataProvider(Protocol):
    name: str

    def fetch_comps(self, db: Session, niche: Niche, platform: str, title: str, region: str, completeness: str,
                    since: datetime) -> list[Comp]: ...


def _db_comps(db: Session, provider: str, niche: Niche, platform: str, title: str, region: str, completeness: str,
              since: datetime, weight: float = 1.0) -> list[Comp]:
    rows = db.scalars(select(SoldComp).where(
        SoldComp.niche_id == niche.id, SoldComp.provider == provider, SoldComp.platform == platform,
        SoldComp.sold_at >= since,
    )).all()
    out = []
    for r in rows:
        if region not in ("", "unknown") and r.region and r.region != region:
            continue
        if completeness not in ("", "unknown") and r.completeness and r.completeness != completeness:
            continue
        sim = fuzz.token_set_ratio(r.title.lower(), title.lower())
        if sim >= 85:
            out.append(Comp(price=r.sold_price, sold_at=r.sold_at, weight=weight * r.weight, provider=provider, title=r.title))
    return out


class MockSoldProvider:
    name = "mock"

    def fetch_comps(self, db, niche, platform, title, region, completeness, since):
        return _db_comps(db, "mock", niche, platform, title, region, completeness, since)


class CsvImportProvider:
    """Comps imported from CSV uploads (stored with provider='csv')."""
    name = "csv"
    REQUIRED = {"title", "sold_price", "sold_at"}

    def fetch_comps(self, db, niche, platform, title, region, completeness, since):
        return _db_comps(db, "csv", niche, platform, title, region, completeness, since)

    @classmethod
    def import_csv(cls, db: Session, niche: Niche, content: str, default_platform: str = "") -> int:
        """Columns: title, sold_price, sold_at, [platform], [region], [completeness], [postage], [id].
        Terapeak exports use 'Title', 'Sold Price', 'Date Sold' - header names are normalised."""
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        for row in reader:
            r = {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
            r.setdefault("sold_price", r.get("price", r.get("sale_price", "")))
            r.setdefault("sold_at", r.get("date_sold", r.get("date", "")))
            if not cls.REQUIRED.issubset(r) or not r["title"]:
                continue
            try:
                price = float(str(r["sold_price"]).replace("£", "").replace(",", ""))
                sold_at = _parse_date(r["sold_at"])
            except ValueError:
                continue
            platform = r.get("platform") or default_platform
            if not platform:
                from app.identification.normaliser import _platform_from_text
                platform = _platform_from_text(r["title"], (niche.config or {}).get("platforms", {}))
            ext = r.get("id") or r.get("item_id") or f"csv-{abs(hash((r['title'], price, sold_at)))}"
            if db.scalar(select(SoldComp.id).where(SoldComp.provider == "csv", SoldComp.external_id == ext)):
                continue
            db.add(SoldComp(niche_id=niche.id, provider="csv", external_id=ext, platform=platform, title=r["title"][:200],
                            region=r.get("region", ""), completeness=r.get("completeness", ""), sold_price=price,
                            postage=float(r.get("postage") or 0), sold_at=sold_at))
            count += 1
        db.flush()
        return count


def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%d %b %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    raise ValueError(s)


class OwnSalesProvider:
    """My own sales from Module 5. Weight grows with the number of own sales (max 3x)."""
    name = "own_sales"

    def fetch_comps(self, db, niche, platform, title, region, completeness, since):
        rows = db.execute(
            select(Sale, InventoryItem).join(InventoryItem, Sale.inventory_item_id == InventoryItem.id)
            .where(InventoryItem.niche_id == niche.id, InventoryItem.platform == platform, Sale.sold_at >= since)
        ).all()
        matches = [(s, i) for s, i in rows if fuzz.token_set_ratio(i.title.lower(), title.lower()) >= 85
                   and (completeness in ("", "unknown") or not i.completeness or i.completeness == completeness)]
        weight = min(3.0, 1.0 + 0.25 * len(matches))
        return [Comp(price=s.sale_price, sold_at=s.sold_at, weight=weight, provider="own_sales", title=i.title) for s, i in matches]


class EbayMarketplaceInsightsProvider:
    """eBay Marketplace Insights API (restricted). Real call when enabled + keys; otherwise returns nothing."""
    name = "ebay_insights"

    def __init__(self, auth=None, enabled: bool = False):
        self.auth, self.enabled = auth, enabled

    def fetch_comps(self, db, niche, platform, title, region, completeness, since):
        if not self.enabled or self.auth is None:
            return []
        try:
            r = httpx.get(
                f"{self.auth.host}/buy/marketplace_insights/v1_beta/item_sales/search",
                headers={"Authorization": f"Bearer {self.auth.token()}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"},
                params={"q": f"{title} {platform}", "filter": "lastSoldDate:[{}..]".format(since.strftime("%Y-%m-%dT%H:%M:%SZ")), "limit": 100},
                timeout=30,
            )
            if r.status_code != 200:
                log.warning("Marketplace Insights HTTP %s", r.status_code)
                return []
            out = []
            for it in r.json().get("itemSales", []):
                price = float(it.get("lastSoldPrice", {}).get("value", 0) or 0)
                sold = it.get("lastSoldDate")
                if price and sold and fuzz.token_set_ratio(it.get("title", "").lower(), title.lower()) >= 80:
                    out.append(Comp(price=price, sold_at=datetime.fromisoformat(sold.replace("Z", "+00:00")).replace(tzinfo=None),
                                    provider=self.name, title=it.get("title", "")))
            return out
        except httpx.HTTPError as e:
            log.warning("Marketplace Insights failed: %s", e)
            return []


def default_providers() -> list[SoldDataProvider]:
    s = get_settings()
    providers: list[SoldDataProvider] = [CsvImportProvider(), OwnSalesProvider()]
    if s.ebay_marketplace_insights_enabled and not s.ebay_is_mock:
        from app.sourcing.ebay_browse import EbayAuth
        providers.append(EbayMarketplaceInsightsProvider(EbayAuth(s.ebay_client_id, s.ebay_client_secret, s.ebay_env), True))
    if s.mock_mode or s.ebay_is_mock:
        providers.append(MockSoldProvider())
    return providers


@dataclass
class ValuationResult:
    median: float
    p25: float
    p75: float
    sold_count: int
    active_count: int
    sell_through: float
    est_days: int
    confidence: str
    confidence_score: float
    providers: dict


def _weighted_quantile(values: list[tuple[float, float]], q: float) -> float:
    vals = sorted(values)
    total = sum(w for _, w in vals)
    if total <= 0:
        return 0.0
    acc = 0.0
    for v, w in vals:
        acc += w
        if acc >= q * total:
            return v
    return vals[-1][0]


def estimate_days_to_sell(sold_count: int, active_count: int, window_days: int) -> int:
    """Queue model: a new listing competes with `active_count` others at `sold_count/window` sales per day.
    Priced at the median, ours should clear in roughly 40% of the full-queue time. Clamped to 3..365."""
    if sold_count <= 0:
        return 365
    per_day = sold_count / window_days
    days = (max(active_count, 1) / per_day) * 0.4
    return int(min(365, max(3, round(days))))


def compute_valuation(comps: list[Comp], active_count: int, window_days: int = 90) -> ValuationResult:
    providers: dict[str, int] = {}
    for c in comps:
        providers[c.provider] = providers.get(c.provider, 0) + 1
    if not comps:
        return ValuationResult(0, 0, 0, 0, active_count, 0.0, 365, "low", 0.0, providers)
    pairs = [(c.price, c.weight) for c in comps]
    median = _weighted_quantile(pairs, 0.5)
    p25, p75 = _weighted_quantile(pairs, 0.25), _weighted_quantile(pairs, 0.75)
    n = len(comps)
    str_ = n / (n + active_count) if (n + active_count) else 0.0
    days = estimate_days_to_sell(n, active_count, window_days)
    if n < 5:
        conf, score = "low", min(0.4, n / 10)
    elif n < 15:
        conf, score = "medium", 0.4 + (n - 5) / 25
    else:
        conf, score = "high", min(1.0, 0.8 + (n - 15) / 100)
    spread = (p75 - p25) / median if median else 1
    if spread > 0.6 and conf == "high":
        conf, score = "medium", score * 0.8
    return ValuationResult(round(median, 2), round(p25, 2), round(p75, 2), n, active_count, round(str_, 3), days, conf, round(score, 2), providers)


def active_listing_count(platform: str, title: str, completeness: str) -> int:
    s = get_settings()
    if s.ebay_is_mock:
        from app.seed import active_count_for
        return active_count_for(platform, title, completeness)
    try:  # pragma: no cover - network
        from app.sourcing.ebay_browse import build_ebay_watcher
        return build_ebay_watcher().active_count(f"{title} {platform}")
    except Exception as e:
        log.warning("active count failed: %s", e)
        return 0


def value_item(db: Session, niche: Niche, platform: str, title: str, region: str, completeness: str,
               providers: Optional[list[SoldDataProvider]] = None, use_cache: bool = True) -> Valuation:
    """Valuation with per-item cache."""
    from app.identification.normaliser import item_key
    key = item_key(niche.slug, platform, title, region, completeness)
    now = datetime.utcnow()
    if use_cache:
        cached = db.scalar(select(Valuation).where(Valuation.item_key == key, Valuation.expires_at > now).order_by(Valuation.created_at.desc()))
        if cached:
            return cached
    window = int(get_setting(db, "comp_window_days", 90))
    since = now - timedelta(days=window)
    comps: list[Comp] = []
    for p in providers or default_providers():
        try:
            comps.extend(p.fetch_comps(db, niche, platform, title, region, completeness, since))
        except Exception as e:  # pragma: no cover
            log.warning("provider %s failed: %s", p.name, e)
    # Fall back to any completeness if we have nothing for the exact one
    if not comps and completeness not in ("", "unknown"):
        for p in providers or default_providers():
            comps.extend(p.fetch_comps(db, niche, platform, title, region, "", since))
        if comps:
            adj = {"loose": 0.6, "boxed": 0.85, "cib": 1.0, "sealed": 2.0, "graded": 3.0}.get(completeness, 1.0)
            comps = [Comp(c.price * adj, c.sold_at, c.weight * 0.5, c.provider, c.title) for c in comps]
    active = active_listing_count(platform, title, completeness)
    res = compute_valuation(comps, active, window)
    ttl = int(get_setting(db, "valuation_cache_hours", 24))
    row = Valuation(item_key=key, niche_id=niche.id, median_price=res.median, p25=res.p25, p75=res.p75,
                    sold_count=res.sold_count, active_count=res.active_count, sell_through_rate=res.sell_through,
                    est_days_to_sell=res.est_days, confidence=res.confidence, confidence_score=res.confidence_score,
                    providers=res.providers, expires_at=now + timedelta(hours=ttl))
    db.add(row)
    db.flush()
    return row


def value_bundle(db: Session, niche: Niche, items: list[dict], providers=None) -> tuple[float, int, str, list[dict]]:
    """Sum of parts for a bundle. Returns (total_median, est_days, confidence, per-item breakdown)."""
    total, days, parts = 0.0, [], []
    confs = []
    for it in items:
        v = value_item(db, niche, it.get("platform", "unknown"), it.get("title", ""), it.get("region", "PAL"),
                       it.get("completeness", "loose"), providers)
        total += v.median_price
        days.append(v.est_days_to_sell)
        confs.append(v.confidence_score)
        parts.append({"platform": it.get("platform"), "title": it.get("title"), "completeness": it.get("completeness"),
                      "median": v.median_price, "days": v.est_days_to_sell, "confidence": v.confidence})
    if not parts:
        return 0.0, 365, "low", []
    avg_conf = sum(confs) / len(confs)
    conf = "high" if avg_conf >= 0.8 else "medium" if avg_conf >= 0.4 else "low"
    # Selling a bundle as separate lots takes about as long as the slowest common item, capped by average
    est = int(round(sum(days) / len(days)))
    return round(total, 2), est, conf, parts


def seed_mock_comps(db: Session, niche: Niche) -> int:
    from app.seed import seed_sold_comps
    if db.scalar(select(SoldComp.id).where(SoldComp.provider == "mock").limit(1)):
        return 0
    n = 0
    for c in seed_sold_comps():
        db.add(SoldComp(niche_id=niche.id, **c))
        n += 1
    db.flush()
    return n
