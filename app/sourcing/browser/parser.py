"""Selector-driven HTML parser. Pure functions so it can be tested with fixture HTML offline."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup, Tag

from app.sourcing.base import RawListing

SELECTOR_DIR = Path(__file__).parent / "selectors"
PRICE_RE = re.compile(r"£\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)")
POSTCODE_DISTRICT_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b(?:\s*\d[A-Z]{2})?", re.I)
COLLECTION_RE = re.compile(r"collection only|collect only|cash on collection|collection in person|pick ?up only|no posting|will not post|can'?t post", re.I)
POST_RE = re.compile(r"can post|will post|happy to post|postage available|delivery available|free postage|\+\s?£\d", re.I)


def load_selectors(site: str) -> dict:
    with (SELECTOR_DIR / f"{site}.yaml").open() as fh:
        return yaml.safe_load(fh)


def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    m = PRICE_RE.search(text.replace(" ", " "))
    if not m:
        m2 = re.search(r"(\d+(?:\.\d{1,2})?)", text)
        return float(m2.group(1)) if m2 and "free" not in text.lower() else None
    return float(m.group(1).replace(",", ""))


def extract_postcode_district(text: str) -> str:
    if not text:
        return ""
    m = POSTCODE_DISTRICT_RE.search(text.upper())
    return m.group(1).upper() if m else ""


def _css_list(sel: str) -> list[str]:
    return [s.strip() for s in sel.split(",") if s.strip() and not s.strip().startswith("text=")]


def _select_first(node: Tag, sel: str) -> Optional[Tag]:
    for s in _css_list(sel):
        try:
            found = node.select_one(s)
        except Exception:
            continue
        if found is not None:
            return found
    return None


def _select_all(node: Tag, sel: str) -> list[Tag]:
    for s in _css_list(sel):
        try:
            found = node.select(s)
        except Exception:
            continue
        if found:
            return found
    return []


def _text(node: Optional[Tag], attr: Optional[str] = None) -> str:
    if node is None:
        return ""
    if attr and node.get(attr):
        return str(node.get(attr)).strip()
    return node.get_text(" ", strip=True)


def _external_id(url: str, regex: str) -> str:
    m = re.search(regex, url)
    return m.group(1) if m else re.sub(r"\W+", "_", url)[-60:]


def parse_search_results(site: str, html: str, selectors: dict | None = None) -> list[RawListing]:
    cfg = selectors or load_selectors(site)
    r = cfg["results"]
    soup = BeautifulSoup(html, "lxml")
    out: list[RawListing] = []
    seen: set[str] = set()
    for item in _select_all(soup, r["item"]):
        link = item if r.get("link") == "self" else _select_first(item, r.get("link", "a"))
        href = link.get("href") if link is not None else None
        if not href:
            continue
        url = urljoin(cfg["base_url"], str(href))
        ext_id = _external_id(url, r.get("external_id_regex", r"(\d+)"))
        if ext_id in seen:
            continue
        seen.add(ext_id)
        title_node = _select_first(item, r.get("title", "a"))
        title = _text(title_node, r.get("title_attr"))
        if not title and link is not None:
            title = _text(link, "title") or _text(link, "aria-label")
        price = parse_price(_text(_select_first(item, r.get("price", ""))))
        if price is None:
            price = parse_price(item.get_text(" ", strip=True))
        if price is None:
            continue
        img = _select_first(item, r.get("image", "img"))
        img_url = _text(img, r.get("image_attr", "src")) if img is not None else ""
        location = _text(_select_first(item, r["location"])) if r.get("location") else ""
        out.append(RawListing(
            source=site, external_id=ext_id, url=url, title=title[:300], price=price,
            location_text=location[:120], postcode_district=extract_postcode_district(location),
            image_urls=[img_url] if img_url else [],
            collection_only=site in ("facebook", "gumtree"),
        ))
    return out


def parse_detail(site: str, html: str, url: str, selectors: dict | None = None) -> RawListing:
    cfg = selectors or load_selectors(site)
    d = cfg["detail"]
    r = cfg["results"]
    soup = BeautifulSoup(html, "lxml")
    title = _text(_select_first(soup, d.get("title", "h1")))
    price = parse_price(_text(_select_first(soup, d.get("price", "")))) or 0.0
    description = _text(_select_first(soup, d.get("description", "")))[:4000]
    location = _text(_select_first(soup, d.get("location", "")))
    seller = _text(_select_first(soup, d.get("seller", "")))
    condition = _text(_select_first(soup, d.get("condition", ""))) if d.get("condition") else ""
    images = [str(i.get("src") or i.get("data-src") or "") for i in _select_all(soup, d.get("images", "img"))]
    images = [i for i in images if i.startswith("http")][:12]
    blob = f"{title} {description}"
    if site in ("facebook", "gumtree"):
        collection_only = not POST_RE.search(blob)
    else:
        collection_only = bool(COLLECTION_RE.search(blob)) and not POST_RE.search(blob)
    postage = None
    m = re.search(r"\+\s?£(\d+(?:\.\d{2})?)\s*(?:shipping|postage|delivery)", blob, re.I)
    if m:
        postage = float(m.group(1))
    elif re.search(r"free (postage|shipping|delivery)", blob, re.I):
        postage = 0.0
    return RawListing(
        source=site, external_id=_external_id(url, r.get("external_id_regex", r"(\d+)")), url=url, title=title[:300],
        price=price, description=description, location_text=location[:120],
        postcode_district=extract_postcode_district(location), seller_name=seller[:100], image_urls=images,
        condition_text=condition[:60], collection_only=collection_only, postage_cost=postage,
    )


def detect_block(site: str, html: str, page_text: str = "", selectors: dict | None = None) -> Optional[tuple[str, str]]:
    """Return (status, message) if the page is a captcha / login wall / block, else None."""
    cfg = selectors or load_selectors(site)
    soup = BeautifulSoup(html, "lxml")
    text = page_text or soup.get_text(" ", strip=True)
    for status, key in (("needs_login", "login_wall"), ("paused", "captcha"), ("blocked", "blocked")):
        for sig in cfg.get("block_signals", {}).get(key, []):
            if sig.startswith("text="):
                if sig[5:].lower() in text.lower():
                    return status, f"{cfg['site'].title()} shows '{sig[5:]}' - {_human(key)}"
            else:
                try:
                    if soup.select_one(sig) is not None:
                        return status, f"{cfg['site'].title()} matched '{sig}' - {_human(key)}"
                except Exception:
                    continue
    return None


def _human(key: str) -> str:
    return {"login_wall": "needs you to log in / check the browser", "captcha": "shows a CAPTCHA, please solve it by hand in the helper browser",
            "blocked": "appears to be blocking requests; paused"}[key]
