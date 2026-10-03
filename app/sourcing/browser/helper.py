"""Playwright browser helper: persistent logged-in profile, human pacing, pause-on-block.

Safety rules (enforced here, not optional):
  * Only navigates to search-result and listing pages (GET navigation; no clicks on buy/message).
  * Never logs in automatically, never solves CAPTCHAs, no proxies, no fingerprint spoofing.
  * Randomised delays, hourly page-load cap, quiet hours.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote_plus

from app.config import get_settings
from app.sourcing.base import RawListing, SourceError, SourcePaused
from app.sourcing.browser import parser

log = logging.getLogger(__name__)


def in_quiet_hours(quiet: str, now: Optional[datetime] = None) -> bool:
    """quiet like '23-07' (local time). Returns True if now is inside the window."""
    if not quiet or "-" not in quiet:
        return False
    try:
        start, end = (int(x) for x in quiet.split("-"))
    except ValueError:
        return False
    h = (now or datetime.now()).hour
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end


class RateLimiter:
    """Hourly page-load budget + randomised inter-request delay."""

    def __init__(self, min_delay: int, max_delay: int, max_per_hour: int, sleep: Callable[[float], None] = time.sleep):
        self.min_delay, self.max_delay, self.max_per_hour = min_delay, max_delay, max_per_hour
        self._sleep = sleep
        self._window_start = time.time()
        self._count = 0
        self._last = 0.0

    def budget_left(self) -> int:
        if time.time() - self._window_start > 3600:
            self._window_start, self._count = time.time(), 0
        return max(0, self.max_per_hour - self._count)

    def wait(self) -> None:
        if self.budget_left() <= 0:
            raise SourcePaused("paused", "hourly page-load budget used up; resumes next hour")
        if self._last:
            delay = random.uniform(self.min_delay, self.max_delay)
            elapsed = time.time() - self._last
            if elapsed < delay:
                self._sleep(delay - elapsed)
        self._last = time.time()
        self._count += 1


class BrowserSession:
    """Lazy Playwright persistent context. One per process; thread-safe enough for the scheduler's single worker."""

    def __init__(self, profile_dir: str, headless: bool = True):
        self.profile_dir = profile_dir
        self.headless = headless
        self._pw = None
        self._ctx = None

    def _ensure(self):
        if self._ctx is not None:
            return self._ctx
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise SourceError(f"playwright not installed: {e}")
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir, headless=self.headless, viewport={"width": 1280, "height": 900},
            locale="en-GB", timezone_id="Europe/London",
        )
        return self._ctx

    def get_html(self, url: str, wait_selector: Optional[str] = None, timeout_ms: int = 30000) -> tuple[str, str]:
        ctx = self._ensure()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            page.wait_for_timeout(random.randint(1500, 4000))  # let lazy content settle
            for _ in range(random.randint(1, 3)):             # gentle human-like scroll
                page.mouse.wheel(0, random.randint(400, 900))
                page.wait_for_timeout(random.randint(400, 1200))
            return page.content(), page.inner_text("body")
        except SourcePaused:
            raise
        except Exception as e:
            raise SourceError(f"navigation failed: {e}")

    def close(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._ctx = self._pw = None


_shared_session: Optional[BrowserSession] = None


def shared_session() -> BrowserSession:
    global _shared_session
    if _shared_session is None:
        s = get_settings()
        _shared_session = BrowserSession(s.browser_profile_dir, s.browser_headless)
    return _shared_session


class BrowserSiteWatcher:
    """Generic SourceWatcher driven entirely by the site's selector YAML."""

    def __init__(self, site: str, session: Optional[BrowserSession] = None, limiter: Optional[RateLimiter] = None,
                 quiet_hours: str = "", selectors: Optional[dict] = None, fetch_details: bool = True):
        self.slug = site
        self.cfg = selectors or parser.load_selectors(site)
        self.session = session
        s = get_settings()
        self.limiter = limiter or RateLimiter(s.browser_min_delay_s, s.browser_max_delay_s, s.browser_max_page_loads_per_hour)
        self.quiet_hours = quiet_hours or s.browser_quiet_hours
        self.fetch_details = fetch_details

    def _load(self, url: str) -> tuple[str, str]:
        if in_quiet_hours(self.quiet_hours):
            raise SourcePaused("paused", "quiet hours")
        self.limiter.wait()
        session = self.session or shared_session()
        html, text = session.get_html(url, wait_selector=self.cfg["results"]["item"].split(",")[0])
        block = parser.detect_block(self.slug, html, text, self.cfg)
        if block:
            raise SourcePaused(*block)
        return html, text

    def build_search_url(self, query: str, filters: dict) -> str:
        return self.cfg["search_url"].format(
            query=quote_plus(query), max_price=filters.get("max_price", ""), min_price=filters.get("min_price", ""),
            location_slug=self.cfg.get("location_slug", ""),
        )

    def search(self, query: str, filters: dict) -> list[RawListing]:
        html, _ = self._load(self.build_search_url(query, filters))
        results = parser.parse_search_results(self.slug, html, self.cfg)
        max_price = filters.get("max_price")
        if max_price:
            results = [r for r in results if r.price <= float(max_price)]
        return results

    def fetch_detail(self, url: str) -> RawListing:
        html, _ = self._load(url)
        return parser.parse_detail(self.slug, html, url, self.cfg)


class FixtureBrowserWatcher(BrowserSiteWatcher):
    """Offline watcher that parses fixture HTML files (tests + MOCK_MODE)."""

    def __init__(self, site: str, search_html: str, detail_html: dict[str, str] | None = None):
        super().__init__(site, session=None, limiter=RateLimiter(0, 0, 10_000), quiet_hours="")
        self.search_html, self.detail_html = search_html, detail_html or {}

    def _load(self, url: str):
        html = self.detail_html.get(url, self.search_html)
        block = parser.detect_block(self.slug, html, "", self.cfg)
        if block:
            raise SourcePaused(*block)
        return html, ""


BROWSER_SITES = ["facebook", "vinted", "gumtree", "shpock", "depop"]
