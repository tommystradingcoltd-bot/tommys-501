"""eBay Sell APIs (Inventory + Offer + Fulfilment) behind an interface; mocked until a user token exists.

Real flow: createOrReplaceInventoryItem(sku) -> createOffer -> publishOffer. Ending: withdrawOffer.
Sales: Fulfilment getOrders (filter by SKU) -> record_sale. Never bids/buys - sell side only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class PublishedListing:
    external_id: str
    url: str


class EbaySellClient(Protocol):
    name: str

    def publish(self, sku: str, title: str, description: str, price: float, specifics: dict, condition: str,
                image_urls: list[str]) -> PublishedListing: ...

    def end(self, external_id: str) -> bool: ...

    def fetch_orders(self, since_iso: str) -> list[dict]: ...


class MockEbaySellClient:
    name = "mock_ebay"

    def __init__(self):
        self.published: dict[str, dict] = {}
        self.ended: list[str] = []
        self._n = 1000

    def publish(self, sku, title, description, price, specifics, condition, image_urls) -> PublishedListing:
        self._n += 1
        ext = f"mock-offer-{self._n}"
        self.published[ext] = {"sku": sku, "title": title, "price": price}
        return PublishedListing(external_id=ext, url=f"https://www.ebay.co.uk/itm/{self._n}")

    def end(self, external_id: str) -> bool:
        self.ended.append(external_id)
        return True

    def fetch_orders(self, since_iso: str) -> list[dict]:
        return []


class RealEbaySellClient:
    name = "ebay"

    def __init__(self, user_token: str, env: str = "production", marketplace: str = "EBAY_GB"):
        from app.sourcing.ebay_browse import API_HOSTS
        self.host = API_HOSTS.get(env, API_HOSTS["production"])
        self.token, self.marketplace = user_token, marketplace

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Content-Language": "en-GB",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace}

    def publish(self, sku, title, description, price, specifics, condition, image_urls) -> PublishedListing:
        s = get_settings()
        inv = {"availability": {"shipToLocationAvailability": {"quantity": 1}}, "condition": "USED_GOOD" if condition != "new" else "NEW",
               "product": {"title": title[:80], "description": description, "aspects": {k: [v] for k, v in specifics.items()},
                           "imageUrls": image_urls[:12]}}
        r = httpx.put(f"{self.host}/sell/inventory/v1/inventory_item/{sku}", headers=self._h(), json=inv, timeout=30)
        r.raise_for_status()
        offer = {"sku": sku, "marketplaceId": self.marketplace, "format": "FIXED_PRICE", "availableQuantity": 1,
                 "pricingSummary": {"price": {"value": f"{price:.2f}", "currency": "GBP"}},
                 "listingPolicies": {"fulfillmentPolicyId": s.__dict__.get("ebay_fulfillment_policy_id", ""),
                                     "paymentPolicyId": s.__dict__.get("ebay_payment_policy_id", ""),
                                     "returnPolicyId": s.__dict__.get("ebay_return_policy_id", "")},
                 "categoryId": specifics.get("CategoryId", "139973"), "merchantLocationKey": "default"}
        r = httpx.post(f"{self.host}/sell/inventory/v1/offer", headers=self._h(), json=offer, timeout=30)
        r.raise_for_status()
        offer_id = r.json()["offerId"]
        r = httpx.post(f"{self.host}/sell/inventory/v1/offer/{offer_id}/publish", headers=self._h(), timeout=30)
        r.raise_for_status()
        listing_id = r.json().get("listingId", "")
        return PublishedListing(external_id=offer_id, url=f"https://www.ebay.co.uk/itm/{listing_id}")

    def end(self, external_id: str) -> bool:
        r = httpx.post(f"{self.host}/sell/inventory/v1/offer/{external_id}/withdraw", headers=self._h(), timeout=30)
        return r.status_code in (200, 204)

    def fetch_orders(self, since_iso: str) -> list[dict]:
        r = httpx.get(f"{self.host}/sell/fulfillment/v1/order", headers=self._h(),
                      params={"filter": f"creationdate:[{since_iso}..]", "limit": 50}, timeout=30)
        r.raise_for_status()
        out = []
        for o in r.json().get("orders", []):
            for li in o.get("lineItems", []):
                fees = sum(float(f.get("amount", {}).get("value", 0)) for f in o.get("totalMarketplaceFee", [{}]) if isinstance(f, dict)) if isinstance(o.get("totalMarketplaceFee"), list) else float((o.get("totalMarketplaceFee") or {}).get("value", 0) or 0)
                out.append({"order_id": o["orderId"], "sku": li.get("sku", ""), "price": float(li["lineItemCost"]["value"]),
                            "postage_charged": float(li.get("deliveryCost", {}).get("shippingCost", {}).get("value", 0) or 0),
                            "fees": fees, "sold_at": o["creationDate"]})
        return out


_client: EbaySellClient | None = None


def get_ebay_sell() -> EbaySellClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = MockEbaySellClient() if (s.mock_mode or not s.ebay_sell_oauth_token) else RealEbaySellClient(s.ebay_sell_oauth_token, s.ebay_env, s.ebay_marketplace_id)
    return _client


def set_ebay_sell(c: EbaySellClient | None) -> None:
    global _client
    _client = c
