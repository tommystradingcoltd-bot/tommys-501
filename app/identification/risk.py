"""Risk flags: rule-based checks (always run) + optional Claude pass merged in."""
from __future__ import annotations

from typing import Any

from app.identification.llm import get_llm

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


def rule_based_flags(v: dict[str, Any]) -> list[dict]:
    cfg = v.get("niche_config", {}) or {}
    kw = cfg.get("risk_keywords", {})
    text = f"{v.get('title', '')} {v.get('description', '')} {v.get('condition', '')}".lower()
    norm = v.get("normalised", {}) or {}
    flags: list[dict] = []

    def add(code, label, severity, detail=""):
        if not any(f["code"] == code for f in flags):
            flags.append({"code": code, "label": label, "severity": severity, "detail": detail})

    for word in kw.get("repro", []):
        if word in text:
            add("repro", "Likely reproduction / unofficial cart", "high", f"wording: '{word}'")
    for word in kw.get("untested", []):
        if word in text:
            sev = "high" if any(x in word for x in ("faulty", "not working", "parts", "spares")) else "medium"
            add("untested" if sev == "medium" else "faulty", "Untested / sold as seen" if sev == "medium" else "Faulty / spares or repair", sev, f"wording: '{word}'")
    for word in kw.get("missing_manual", []):
        if word in text:
            add("missing_manual", "Missing manual / incomplete", "low", f"wording: '{word}'")
    for word in kw.get("stolen_signals", []):
        if word in text:
            add("stolen_signals", "Stolen-goods warning signs", "high", f"wording: '{word}'")
    for word in kw.get("stock_photo", []):
        if word in text:
            add("stock_photo", "Photos may be stock images", "medium", f"wording: '{word}'")
    if str(v.get("condition", "")).lower() in ("new", "brand new") and norm.get("category") == "game" and norm.get("platform") not in ("", "unknown"):
        add("repro", "'New' retro cart is a classic repro signal", "high", "condition stated as new")
    fb = v.get("seller_feedback")
    if fb is not None and str(fb).isdigit() and int(fb) < 10 and v.get("source") == "ebay":
        add("new_seller", "Seller has under 10 feedback", "low", f"feedback {fb}")
    region = norm.get("region", "")
    if region in ("NTSC-U", "NTSC-J") and "pal" in text:
        add("region_mismatch", "Region wording conflicts (PAL vs NTSC)", "medium")
    elif region in ("NTSC-U", "NTSC-J"):
        add("region_mismatch", f"{region} import - check it runs on UK consoles / buyer demand", "low")
    # too-good-to-be-true on known expensive titles
    try:
        median = float(v.get("median") or 0) or None
    except (TypeError, ValueError):
        median = None
    price = float(v.get("price") or 0)
    fraction = float(cfg.get("repro_price_fraction", 0.25))
    expensive = cfg.get("expensive_titles", [])
    if median and price and price < float(median) * fraction and any(t in text for t in expensive):
        add("too_good", "Price far below market for a rare title - likely fake or scam", "high", f"£{price:.0f} vs median £{float(median):.0f}")
    if norm.get("is_bundle") and norm.get("confidence", 1) < 0.5:
        add("unclear_bundle", "Bundle contents unclear - check photos", "medium")
    return flags


def assess_risk(listing, item, niche, median: float | None, source_slug: str = "") -> list[dict]:
    cfg = niche.config or {}
    variables = {
        "title": listing.title, "description": listing.description, "condition": listing.condition_text,
        "seller_feedback": listing.seller_feedback if listing.seller_feedback is not None else "unknown",
        "price": f"{listing.price:.2f}", "median": f"{median:.2f}" if median else "unknown",
        "normalised": {"platform": item.platform, "title": item.title, "region": item.region, "completeness": item.completeness,
                        "category": item.category, "is_bundle": item.is_bundle, "confidence": item.confidence},
        "niche_config": cfg, "source": source_slug,
    }
    flags = rule_based_flags(variables)
    llm = get_llm()
    if llm.name != "mock":
        try:
            extra = llm.complete_json("risk_flags", variables).get("flags", [])
            for f in extra:
                if isinstance(f, dict) and f.get("code") and not any(x["code"] == f["code"] for x in flags):
                    flags.append({"code": f["code"], "label": f.get("label", f["code"]), "severity": f.get("severity", "medium"), "detail": f.get("detail", "")})
        except Exception:  # pragma: no cover
            pass
    flags.sort(key=lambda f: -SEVERITY_ORDER.get(f["severity"], 0))
    return flags


def max_severity(flags: list[dict]) -> str:
    if not flags:
        return "none"
    return max(flags, key=lambda f: SEVERITY_ORDER.get(f["severity"], 0))["severity"]
