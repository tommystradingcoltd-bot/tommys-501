"""Common SourceWatcher interface and RawListing transport type."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@dataclass
class RawListing:
    source: str
    external_id: str
    url: str
    title: str
    price: float
    currency: str = "GBP"
    description: str = ""
    listing_type: str = "bin"               # bin | auction
    ends_at: Optional[datetime] = None
    postage_cost: Optional[float] = None    # None = unknown / not stated
    collection_only: bool = False
    location_text: str = ""
    postcode_district: str = ""
    seller_name: str = ""
    seller_feedback: Optional[int] = None
    image_urls: list[str] = field(default_factory=list)
    condition_text: str = ""
    raw: dict = field(default_factory=dict)
    posted_at: Optional[datetime] = None


class SourceError(Exception):
    """Transient failure; the runner will retry with backoff."""


class SourcePaused(Exception):
    """The source must be paused (captcha, block, login wall). `status` is needs_login|blocked|paused."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@runtime_checkable
class SourceWatcher(Protocol):
    slug: str

    def search(self, query: str, filters: dict) -> list[RawListing]: ...

    def fetch_detail(self, url: str) -> RawListing: ...
