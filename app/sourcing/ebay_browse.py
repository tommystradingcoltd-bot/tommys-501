"""eBay UK via the official Browse API (OAuth client-credentials). Never scrapes eBay."""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from app.config import get_settings
from app.sourcing.base import RawListing, SourceError

log = logging.getLogger(__name__)

API_HOSTS = {"production": "https://api.ebay.com", "sandbox": "https://api.sandbox.ebay.com"}
SCOPE = "https://api.ebay.com/oauth/api_scope"


class EbayAuth:
    """Client-credentials token cache."""

    def __init__(self, client_id: str, client_secret: str, env: str = "production"):
        self.client_id, self.client_secret = client_id, client_secret
        self.host = API_HOSTS.get(env, API_HOSTS["production"])
        self._token: Optional[str] = None
        self._expires = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        r = httpx.post(
            f"{self.host}/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE}, timeout=20,
        )
        if r.status_code != 200:
            raise SourceError(f"eBay OAuth failed: HTTP {r.status_code}")
        data = r.json()
        self._token = data["access_token"]
        self._expires = time.time() + int(data.get("expires_in", 7200))
        return self._token


def _parse_item_summary(it: dict) -> RawListing:
    price = float(it.get("price", {}).get("value", 0) or 0)
    currency = it.get("price", {}).get("currency", "GBP")
    buying = it.get("buyingOptions", []) or []
    listing_type = "auction" if "AUCTION" in buying and "FIXED_PRICE" not in buying else "bin"
    if listing_type == "auction" and it.get("currentBidPrice"):
        price = float(it["currentBidPrice"].get("value", price))
    postage = None
    collection_only = False
    opts = it.get("shippingOptions") or []
    if opts:
        cost = opts[0].get("shippingCost", {})
        if cost.get("value") is not None:
            postage = float(cost["value"])
    pickup = it.get("pickupOptions") or []
    if pickup and not opts:
        collection_only = True
    loc = it.get("itemLocation", {}) or {}
    postcode = (loc.get("postalCode") or "").upper().split(" ")[0]
    location_text = ", ".join(x for x in [loc.get("city"), loc.get("postalCode")] if x)
    ends = it.get("itemEndDate")
    ends_at = datetime.fromisoformat(ends.replace("Z", "+00:00")).replace(tzinfo=None) if ends else None
    images = []
    if it.get("image", {}).get("imageUrl"):
        images.append(it["image"]["imageUrl"])
    for extra in it.get("additionalImages", []) or []:
        if extra.get("imageUrl"):
            images.append(extra["imageUrl"])
    seller = it.get("seller", {}) or {}
    return RawListing(
        source="ebay", external_id=str(it.get("itemId") or it.get("legacyItemId")), url=it.get("itemWebUrl", ""),
        title=it.get("title", ""), price=price, currency=currency, listing_type=listing_type, ends_at=ends_at,
        postage_cost=postage, collection_only=collection_only, location_text=location_text,
        postcode_district=postcode, seller_name=seller.get("username", ""),
        seller_feedback=int(seller.get("feedbackScore", 0) or 0), image_urls=images,
        condition_text=it.get("condition", ""), description=it.get("shortDescription", ""), raw={"buyingOptions": buying},
    )


class EbayBrowseWatcher:
    slug = "ebay"

    def __init__(self, auth: EbayAuth, marketplace: str = "EBAY_GB"):
        self.auth = auth
        self.marketplace = marketplace

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth.token()}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=country=GB",
        }

    def _get(self, path: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                r = httpx.get(f"{self.auth.host}{path}", headers=self._headers(), params=params, timeout=30)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise SourceError(str(e))
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            raise SourceError(f"eBay Browse API HTTP {r.status_code}: {r.text[:200]}")
        raise SourceError("eBay Browse API: retries exhausted")

    def search(self, query: str, filters: dict) -> list[RawListing]:
        """Newest-first BIN plus auctions ending soon. Returns de-duplicated item summaries."""
        max_price = filters.get("max_price")
        min_price = filters.get("min_price", 0)
        price_filter = f"price:[{min_price}..{max_price}],priceCurrency:GBP" if max_price else None
        out: dict[str, RawListing] = {}
        for buying, sort in (("FIXED_PRICE", "newlyListed"), ("AUCTION", "endingSoonest")):
            f = [f"buyingOptions:{{{buying}}}", "itemLocationCountry:GB", "deliveryCountry:GB"]
            if price_filter:
                f.append(price_filter)
            params = {"q": query, "limit": filters.get("limit", 50), "sort": sort, "filter": ",".join(f)}
            if filters.get("category_id"):
                params["category_ids"] = filters["category_id"]
            data = self._get("/buy/browse/v1/item_summary/search", params)
            for it in data.get("itemSummaries", []) or []:
                rl = _parse_item_summary(it)
                out.setdefault(rl.external_id, rl)
        return list(out.values())

    def fetch_detail(self, url: str) -> RawListing:
        item_id = url.rstrip("/").split("/")[-1].split("?")[0]
        data = self._get(f"/buy/browse/v1/item/v1|{item_id}|0", {})
        rl = _parse_item_summary(data)
        rl.description = (data.get("description") or "")[:4000]
        rl.url = url
        return rl

    def active_count(self, query: str, filters: dict | None = None) -> int:
        filters = filters or {}
        f = ["itemLocationCountry:GB"]
        data = self._get("/buy/browse/v1/item_summary/search", {"q": query, "limit": 1, "filter": ",".join(f)})
        return int(data.get("total", 0))


class MockEbayBrowseWatcher:
    """Deterministic in-memory implementation using the seed fixtures."""
    slug = "ebay"

    def __init__(self, listings: list[RawListing] | None = None):
        from app.seed import seed_listings
        self._listings = listings if listings is not None else [l for l in seed_listings() if l.source == "ebay"]

    def search(self, query: str, filters: dict) -> list[RawListing]:
        words = [w for w in query.lower().split() if len(w) > 2]
        return [l for l in self._listings if any(w in l.title.lower() for w in words)]

    def fetch_detail(self, url: str) -> RawListing:
        for l in self._listings:
            if l.url == url:
                return l
        raise SourceError("not found")

    def active_count(self, query: str, filters: dict | None = None) -> int:
        return 12


def build_ebay_watcher():
    s = get_settings()
    if s.ebay_is_mock:
        return MockEbayBrowseWatcher()
    return EbayBrowseWatcher(EbayAuth(s.ebay_client_id, s.ebay_client_secret, s.ebay_env), s.ebay_marketplace_id)
