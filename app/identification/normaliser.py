"""Normalise a raw listing into a structured item (Claude, or rule-based mock)."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.identification.llm import get_llm
from app.models import Niche, NormalisedItem, RawListing

log = logging.getLogger(__name__)

COMPLETENESS_RULES = [
    ("graded", r"\b(vga|wata|graded)\b"),
    ("sealed", r"\b(sealed|bnib|brand new sealed|factory sealed)\b"),
    ("cib", r"\b(cib|complete in box|complete with manual|boxed complete|complete boxed|complete|boxed with manual|with manual and box|box and manual|manual and box|boxed with instructions)\b"),
    ("boxed", r"\b(boxed|with box|in box)\b"),
    ("loose", r"\b(cart only|cartridge only|loose|no box|unboxed|disc only|game only|cart\b)"),
]
REGION_RULES = [
    ("NTSC-J", r"\b(ntsc-?j|japanese|japan|jp version|famicom|super famicom)\b"),
    ("NTSC-U", r"\b(ntsc-?u|ntsc|us import|usa|us version|american)\b"),
    ("PAL", r"\b(pal|uk|ukv|european)\b"),
]
BUNDLE_RE = re.compile(r"\b(job ?lot|bundle|collection|lot of|x\s?\d+\b|\d+\s?x\b|\d+\s+games|games? bundle)\b", re.I)
CONSOLE_RE = re.compile(r"\b(console|system|handheld|dmg-01|ds lite|advance sp)\b", re.I)
ACCESSORY_RE = re.compile(r"\b(controller|pad|memory card|lead|cable|adapter|power supply|vmu|rumble pak)\b", re.I)
MODEL_RE = re.compile(r"\b(jungle green|atomic purple|grape|ice blue|fire orange|scph-?\d{3,4}|snsp-?\d{3}|dmg-?01|ds lite|advance sp|tribal|mega drive 2|md2|master system ii|psone|ps one)\b")
BRAND_PREFIX_RE = re.compile(r"^(sega|nintendo|sony|original|boxed|retro)\s+", re.I)


def _starts_with_platform(title: str, aliases: list[str]) -> bool:
    t = BRAND_PREFIX_RE.sub("", title.strip().lower())
    t = BRAND_PREFIX_RE.sub("", t)
    return any(t.startswith(a.strip().lower()) for a in aliases)


def _platform_from_text(text: str, platforms: dict[str, list[str]]) -> str:
    t = f" {text.lower()} "
    best, best_len = "unknown", 0
    for name, aliases in platforms.items():
        for a in aliases:
            a_l = a.lower()
            if re.search(r"(?<![a-z0-9])" + re.escape(a_l.strip()) + r"(?![a-z0-9])", t) and len(a_l) > best_len:
                best, best_len = name, len(a_l)
    # Longest alias wins (Game Boy Color beats Game Boy)
    return best


def _known_titles() -> dict[str, list[str]]:
    """Mock helper: canonical titles per platform from the seed market table."""
    from app.seed import MARKET
    out: dict[str, list[str]] = {}
    for (platform, title, _c) in MARKET:
        if title != "console" and title not in out.setdefault(platform, []):
            out[platform].append(title)
    return out


_TITLE_ALIASES = {
    "zelda ocarina of time": "Zelda Ocarina of Time", "ocarina of time": "Zelda Ocarina of Time", "ocarina": "Zelda Ocarina of Time",
    "a link to the past": "Zelda A Link to the Past", "link to the past": "Zelda A Link to the Past",
    "link's awakening": "Zelda Link's Awakening", "links awakening": "Zelda Link's Awakening",
    "goldeneye": "GoldenEye 007", "conker": "Conker's Bad Fur Day", "banjo": "Banjo-Kazooie",
    "sonic 2": "Sonic the Hedgehog 2", "sonic the hedgehog 2": "Sonic the Hedgehog 2", "streets of rage 2": "Streets of Rage 2",
    "sor2": "Streets of Rage 2", "ff7": "Final Fantasy VII", "final fantasy vii": "Final Fantasy VII", "final fantasy 7": "Final Fantasy VII",
    "smash bros melee": "Super Smash Bros Melee", "super smash bros melee": "Super Smash Bros Melee", "double dash": "Mario Kart Double Dash",
    "mario kart 64": "Mario Kart 64", "super mario 64": "Super Mario 64", "super mario world": "Super Mario World", "smw": "Super Mario World",
    "donkey kong country": "Donkey Kong Country", "dkc": "Donkey Kong Country", "street fighter ii turbo": "Street Fighter II Turbo",
    "street fighter 2 turbo": "Street Fighter II Turbo", "super metroid": "Super Metroid", "chrono trigger": "Chrono Trigger",
    "castlevania bloodlines": "Castlevania Bloodlines", "silent hill": "Silent Hill", "resident evil 2": "Resident Evil 2",
    "crash bandicoot": "Crash Bandicoot", "suikoden ii": "Suikoden II", "suikoden 2": "Suikoden II", "tetris": "Tetris",
    "pokemon red": "Pokemon Red", "pokémon red": "Pokemon Red", "pokemon blue": "Pokemon Blue", "pokemon yellow": "Pokemon Yellow",
    "pokemon crystal": "Pokemon Crystal", "pokemon emerald": "Pokemon Emerald", "pokemon firered": "Pokemon FireRed", "firered": "Pokemon FireRed",
    "metroid prime": "Metroid Prime", "luigi's mansion": "Luigi's Mansion", "luigis mansion": "Luigi's Mansion", "shenmue": "Shenmue",
    "panzer dragoon saga": "Panzer Dragoon Saga", "super mario bros 3": "Super Mario Bros 3", "smb3": "Super Mario Bros 3",
}


def _find_titles(text: str) -> list[str]:
    t = text.lower()
    found: list[tuple[int, str]] = []
    for alias, canon in _TITLE_ALIASES.items():
        idx = t.find(alias)
        if idx >= 0 and canon not in [c for _, c in found]:
            found.append((idx, canon))
    found.sort()
    return [c for _, c in found]


def rule_based_normalise(title: str, description: str, niche_config: dict) -> dict[str, Any]:
    text = f"{title}. {description}"
    platforms = niche_config.get("platforms", {})
    platform = _platform_from_text(text, platforms)
    low = text.lower()
    completeness = "unknown"
    for name, pat in COMPLETENESS_RULES:
        if re.search(pat, low):
            completeness = name
            break
    region = "PAL"  # UK default
    for name, pat in REGION_RULES:
        if re.search(pat, low):
            region = name
            break
    titles = _find_titles(text)
    is_console = bool(CONSOLE_RE.search(title)) and not re.search(r"\b(for|compatible)\b", title.lower()[:20])
    if not is_console and platform != "unknown" and MODEL_RE.search(title.lower()):
        is_console = True
    if not is_console and not titles and platform != "unknown" and _starts_with_platform(title, platforms.get(platform, [])):
        is_console = True  # "Sega Dreamcast with controller" - a console with no game named
    is_bundle = bool(BUNDLE_RE.search(title)) or (is_console and len(titles) >= 1) or len(titles) >= 2
    accessories = sorted({m.group(0).lower() for m in ACCESSORY_RE.finditer(low)})
    if is_console and completeness == "unknown":
        completeness = "boxed" if re.search(r"\bboxed\b", low) else "loose"
    if completeness == "unknown":
        completeness = "loose"
    bundle_items: list[dict] = []
    if is_bundle:
        if is_console:
            bundle_items.append({"platform": platform, "title": "console", "completeness": "boxed" if "boxed" in low else "loose"})
        for t in titles:
            tp = platform
            if tp == "unknown":
                tp = next((p for p, ts in _known_titles().items() if t in ts), "unknown")
            bundle_items.append({"platform": tp, "title": t, "completeness": "cib" if completeness == "cib" else "loose"})
        # Multi-platform job lots: assign titles to the right platform
        for p, ts in _known_titles().items():
            for bi in bundle_items:
                if bi["title"] in ts and bi["platform"] != p and p in low:
                    bi["platform"] = p
        category = "bundle"
        canon = "bundle"
    elif is_console:
        category, canon = "console", "console"
    elif titles:
        category, canon = "game", titles[0]
        if platform == "unknown":
            platform = next((p for p, ts in _known_titles().items() if canon in ts), "unknown")
    elif accessories and not titles:
        category, canon = "accessory", accessories[0]
    else:
        category, canon = "game", re.sub(r"\b(pal|ntsc|boxed|cart only|tested|uk|complete|loose)\b", "", title, flags=re.I).strip()[:60] or "unknown"
    model = ""
    m = MODEL_RE.search(low)
    if m:
        model = m.group(1)
    if is_console and not is_bundle and completeness not in ("loose", "boxed"):
        completeness = "boxed" if completeness in ("cib", "sealed") else "loose"
    conf = 0.85 if platform != "unknown" and (titles or is_console) else 0.5
    if is_bundle and not titles:
        conf = 0.35
    cond = []
    for kw in ("untested", "tested", "working", "faulty", "spares or repair", "scratched", "label worn", "faded", "lines", "loose stick", "cracked"):
        if kw in low:
            cond.append(kw)
    return {
        "platform": platform, "title": canon, "category": category, "region": region, "completeness": completeness,
        "condition_notes": ", ".join(cond), "is_bundle": is_bundle, "bundle_items": bundle_items, "console_model": model,
        "accessories": accessories, "confidence": conf,
    }


def item_key(niche_slug: str, platform: str, title: str, region: str, completeness: str) -> str:
    raw = "|".join(x.strip().lower() for x in (niche_slug, platform, title, region, completeness))
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def normalise_listing(db: Session, listing: RawListing, niche: Niche) -> NormalisedItem:
    cfg = niche.config or {}
    llm = get_llm()
    data = llm.complete_json("normalise", {
        "niche_name": niche.name, "platforms": ", ".join(cfg.get("platforms", {}).keys()),
        "hints": cfg.get("normalisation_hints", ""), "title": listing.title, "description": listing.description,
        "condition": listing.condition_text, "price": f"{listing.price:.2f}", "niche_config": cfg,
    })
    platform = data.get("platform") or "unknown"
    title = data.get("title") or listing.title[:60]
    region = data.get("region") or "unknown"
    completeness = data.get("completeness") or "unknown"
    item = NormalisedItem(
        raw_listing_id=listing.id, niche_id=niche.id, platform=platform, title=title[:200], region=region,
        completeness=completeness, condition_notes=(data.get("condition_notes") or "")[:2000],
        is_bundle=bool(data.get("is_bundle")), bundle_items=data.get("bundle_items") or [],
        console_model=(data.get("console_model") or "")[:64], accessories=data.get("accessories") or [],
        category=data.get("category") or "game", confidence=float(data.get("confidence", 0.5)),
        item_key=item_key(niche.slug, platform, title, region, completeness), model_name=llm.name,
    )
    db.add(item)
    db.flush()
    return item
