"""Cross-listing: CSV export in a cross-lister-friendly format + CrossLister interface for a future service."""
from __future__ import annotations

import csv
import io
from typing import Protocol

from app.models import Listing

CSV_COLUMNS = ["sku", "title", "description", "price", "condition", "category", "brand", "platform", "region",
               "completeness", "quantity", "photos", "weight_class", "tags"]


class CrossLister(Protocol):
    name: str

    def push(self, listing: Listing, platforms: list[str]) -> dict[str, str]: ...   # platform -> external id

    def remove(self, platform: str, external_id: str) -> bool: ...


class NoopCrossLister:
    """Placeholder until a cross-listing service (e.g. Vendoo/List Perfectly style) is connected."""
    name = "noop"

    def push(self, listing: Listing, platforms: list[str]) -> dict[str, str]:
        return {}

    def remove(self, platform: str, external_id: str) -> bool:
        return False


def listings_csv(listings: list[Listing]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for l in listings:
        i = l.item
        w.writerow({
            "sku": i.sku, "title": l.title, "description": l.description.replace("\n", " "), "price": f"{l.price:.2f}",
            "condition": "Used", "category": "Video Games & Consoles", "brand": _brand(i.platform), "platform": i.platform,
            "region": i.region, "completeness": i.completeness, "quantity": 1, "photos": "", "weight_class": i.weight_class,
            "tags": " ".join(["retro", i.platform.replace(" ", "").lower(), i.category]),
        })
    return buf.getvalue()


def _brand(platform: str) -> str:
    if platform in ("SNES", "NES", "N64", "GameCube", "DS", "Wii") or "Game Boy" in platform:
        return "Nintendo"
    if platform in ("Mega Drive", "Master System", "Saturn", "Dreamcast", "Game Gear"):
        return "Sega"
    if platform.startswith("PS"):
        return "Sony"
    if "Xbox" in platform:
        return "Microsoft"
    return ""
