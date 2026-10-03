"""Build the SourceWatcher for a source slug, honouring MOCK_MODE and fixtures."""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.sourcing.browser.helper import BROWSER_SITES, BrowserSiteWatcher, FixtureBrowserWatcher, RateLimiter
from app.sourcing.ebay_browse import build_ebay_watcher
from app.sourcing.paid_provider import PaidFeedWatcher

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "html"


def build_watcher(slug: str, source_cfg: dict | None = None):
    s = get_settings()
    cfg = source_cfg or {}
    if slug == "ebay":
        return build_ebay_watcher()
    if slug == "paid_feed":
        return PaidFeedWatcher(api_key=cfg.get("api_key", ""))
    if slug in BROWSER_SITES:
        if s.mock_mode or not s.browser_sources_enabled:
            search = (FIXTURE_DIR / f"{slug}_search.html")
            if search.exists():
                return FixtureBrowserWatcher(slug, search.read_text())
            return None
        limiter = RateLimiter(cfg.get("min_delay_s", s.browser_min_delay_s), cfg.get("max_delay_s", s.browser_max_delay_s),
                              cfg.get("max_page_loads_per_hour", s.browser_max_page_loads_per_hour))
        return BrowserSiteWatcher(slug, limiter=limiter, quiet_hours=cfg.get("quiet_hours", s.browser_quiet_hours))
    return None
