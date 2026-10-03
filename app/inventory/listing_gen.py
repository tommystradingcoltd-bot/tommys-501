"""Listing generator: SEO title (<=80 chars), honest condition copy, item specifics, suggested price with an
auto-markdown schedule, and a photo shot list. Claude writes the copy when configured; the mock is rule-based.
Never calls a reproduction genuine."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.identification.llm import get_llm
from app.models import InventoryItem, Listing, Niche, TestResult
from app.settings_store import get_setting

REPRO_WORDS = ("repro", "reproduction", "unofficial", "bootleg")


def build_title(platform: str, title: str, region: str, completeness: str, extras: list[str]) -> str:
    comp = {"cib": "Complete", "boxed": "Boxed", "loose": "Cart Only" if platform not in ("PS1", "PS2", "Dreamcast", "Saturn", "GameCube", "Xbox") else "Disc Only",
            "sealed": "Sealed", "graded": "Graded"}.get(completeness, "")
    parts = [title, platform, region if region not in ("", "unknown") else "", comp] + extras
    out = " ".join(p for p in parts if p)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > 80:
        out = out[:80].rsplit(" ", 1)[0]
    return out


def rule_based_copy(item: dict[str, Any], tests: list[dict]) -> dict:
    platform, title = item.get("platform", ""), item.get("title", "")
    comp, region = item.get("completeness", ""), item.get("region", "")
    cat = item.get("category", "game")
    notes = item.get("condition_notes", "")
    is_repro = any(w in f"{title} {notes}".lower() for w in REPRO_WORDS)
    extras = ["Tested & Working"] if any(t.get("result") == "pass" and t.get("key") in ("boots", "powers_on", "works") for t in tests) else []
    if is_repro:
        extras = ["REPRODUCTION"] + extras
    if cat == "console":
        name = f"{platform} Console"
        seo = build_title(name, item.get("console_model", ""), region, "Boxed" if comp == "boxed" else "", extras + ["Retro"])
    else:
        seo = build_title(platform, title, region, comp, extras + (["Retro Nintendo"] if "Nintendo" in platform or platform in ("SNES", "NES", "N64", "GameCube") or "Game Boy" in platform else ["Retro Sega"] if platform in ("Mega Drive", "Master System", "Saturn", "Dreamcast", "Game Gear") else []))
    cond_lines = []
    if is_repro:
        cond_lines.append("This is a reproduction cartridge, not an official release. Priced and described as such.")
    if notes:
        cond_lines.append(f"Condition notes: {notes}.")
    test_lines = [f"{t['label']}: {t['result']}" + (f" ({t['notes']})" if t.get("notes") else "") for t in tests if t.get("result")]
    if test_lines:
        cond_lines.append("Tested by us before listing - " + "; ".join(test_lines) + ".")
    else:
        cond_lines.append("Tested before listing where possible; see photos for exact condition.")
    comp_text = {"cib": "Complete with box and manual", "boxed": "Boxed (no manual unless pictured)", "loose": "Cartridge/disc only, no box",
                 "sealed": "Factory sealed", "graded": "Professionally graded"}.get(comp, "See photos")
    description = (
        f"## What you get\n{platform} {title} ({region or 'region as pictured'}). {comp_text}. "
        + (", ".join(item.get("accessories", [])) + " included. " if item.get("accessories") else "")
        + "\n\n## Condition\n" + " ".join(cond_lines)
        + "\n\n## Testing\n" + ("; ".join(test_lines) if test_lines else "Checked and working unless stated otherwise.")
        + "\n\n## Postage\nSent tracked, well packed, within 1 working day. Photos are of the actual item."
    )
    specifics = {"Platform": platform, "Game Name": title if cat != "console" else "", "Region Code": region, "Type": cat.title(),
                 "Features": "Reproduction" if is_repro else ("Complete" if comp == "cib" else ""), "Model": item.get("console_model", "")}
    return {"title": seo, "condition_description": " ".join(cond_lines), "description": description,
            "item_specifics": {k: v for k, v in specifics.items() if v}}


def markdown_schedule(price: float, expected_days: int, rules: list[dict]) -> list[dict]:
    out = []
    for r in rules:
        day = int(round(expected_days * r["after_days_pct"] / 100))
        out.append({"day": day, "price": round(price * (1 - r["pct_off"]), 2), "pct_off": r["pct_off"]})
    return out


def suggested_price(expected_sale_price: float, uplift: float = 0.0) -> float:
    p = expected_sale_price * (1 + uplift) * 1.04   # list a touch above median to leave room for offers
    if p >= 20:
        return float(int(p)) - 0.01                 # £44.99 style
    return round(p, 2)


def generate_listing(db: Session, item: InventoryItem) -> Listing:
    niche = db.get(Niche, item.niche_id)
    latest_test: TestResult | None = max(item.test_results, key=lambda t: t.tested_at) if item.test_results else None
    tests = latest_test.checklist if latest_test else []
    norm = item.deal.item if item.deal else None
    item_data = {
        "platform": item.platform, "title": item.title, "completeness": item.completeness, "region": item.region,
        "category": item.category, "condition_notes": (norm.condition_notes if norm else "") or (latest_test.notes if latest_test else ""),
        "console_model": norm.console_model if norm else "", "accessories": norm.accessories if norm else [],
        "risk_flags": [f["code"] for f in (norm.risk_flags if norm else [])],
    }
    if "repro" in item_data["risk_flags"] and "repro" not in item_data["condition_notes"].lower():
        item_data["condition_notes"] = ("reproduction cartridge; " + item_data["condition_notes"]).strip("; ")
    copy = get_llm().complete_json("listing_copy", {"item": item_data, "tests": tests, "niche_name": niche.name})
    title = copy.get("title", "")[:80] or build_title(item.platform, item.title, item.region, item.completeness, [])
    if "repro" in item_data["risk_flags"] and "repro" not in title.lower():
        title = ("REPRO " + title)[:80]
    uplift = float(get_setting(db, "listing_quality_uplift", 0.0))
    price = suggested_price(item.expected_sale_price, uplift) if item.expected_sale_price else round(item.cost_basis * 1.6, 2)
    sched = markdown_schedule(price, item.expected_days_to_sell or 30, get_setting(db, "auto_markdown", []))
    shots = (niche.config or {}).get("photo_shot_list", {})
    shot_list = shots.get(item.category) or shots.get("game") or []
    listing = Listing(inventory_item_id=item.id, title=title, description=copy.get("description", ""),
                      condition_description=copy.get("condition_description", ""), item_specifics=copy.get("item_specifics", {}),
                      price=price, markdown_schedule=sched, photo_shot_list=shot_list, status="draft")
    db.add(listing)
    db.flush()
    return listing


def current_markdown_price(listing: Listing, days_listed: int) -> float:
    price = listing.price
    for step in sorted(listing.markdown_schedule, key=lambda s: s["day"]):
        if days_listed >= step["day"]:
            price = step["price"]
    return price
