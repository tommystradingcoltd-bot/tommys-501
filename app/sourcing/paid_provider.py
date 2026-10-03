"""Stub for a future paid data-feed provider.

Drop a real implementation in here (or a new module registered in sourcing.registry) once
the data shows the browser helper is missing too many deals. Keep the SourceWatcher contract.
"""
from __future__ import annotations

from app.sourcing.base import RawListing, SourceError


class PaidFeedWatcher:
    slug = "paid_feed"

    def __init__(self, api_key: str = "", endpoint: str = ""):
        self.api_key = api_key
        self.endpoint = endpoint

    def search(self, query: str, filters: dict) -> list[RawListing]:
        if not self.api_key:
            raise SourceError("Paid feed not configured (PAID_FEED_API_KEY). This is a stub.")
        raise NotImplementedError("Implement against the chosen provider's API")

    def fetch_detail(self, url: str) -> RawListing:
        raise NotImplementedError
