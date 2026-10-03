"""Seed data: 50 realistic UK retro-game listings (good deals, bad deals, fakes, bundles, collection-only)
plus mock sold comps so the whole pipeline runs end-to-end with no external services.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.sourcing.base import RawListing

# Market reference (approximate PAL UK sold medians) keyed by (platform, title keyword, completeness).
# These drive the mock sold comps AND let the seed listings be deliberately good/bad deals.
MARKET: dict[tuple[str, str, str], tuple[float, int, int]] = {
    # (platform, title, completeness): (median £, comps sold in 90d, active listings)
    ("SNES", "Super Mario World", "loose"): (18, 40, 30),
    ("SNES", "Super Mario World", "boxed"): (45, 18, 12),
    ("SNES", "Super Mario World", "cib"): (60, 12, 8),
    ("SNES", "Chrono Trigger", "loose"): (380, 4, 2),
    ("SNES", "Super Metroid", "loose"): (55, 20, 10),
    ("SNES", "Super Metroid", "cib"): (140, 6, 3),
    ("SNES", "Donkey Kong Country", "loose"): (16, 50, 40),
    ("SNES", "Zelda A Link to the Past", "loose"): (35, 30, 15),
    ("SNES", "Zelda A Link to the Past", "cib"): (95, 8, 5),
    ("SNES", "Street Fighter II Turbo", "loose"): (14, 30, 25),
    ("SNES", "console", "loose"): (55, 40, 25),
    ("SNES", "console", "boxed"): (120, 10, 6),
    ("N64", "Mario Kart 64", "loose"): (28, 60, 40),
    ("N64", "GoldenEye 007", "loose"): (18, 70, 60),
    ("N64", "Zelda Ocarina of Time", "loose"): (30, 55, 35),
    ("N64", "Zelda Ocarina of Time", "cib"): (75, 10, 6),
    ("N64", "Conker's Bad Fur Day", "loose"): (85, 8, 4),
    ("N64", "Super Mario 64", "loose"): (30, 60, 45),
    ("N64", "Banjo-Kazooie", "loose"): (25, 35, 20),
    ("N64", "console", "loose"): (60, 45, 30),
    ("N64", "console", "boxed"): (140, 8, 5),
    ("Mega Drive", "Sonic the Hedgehog 2", "loose"): (6, 80, 90),
    ("Mega Drive", "Sonic the Hedgehog 2", "cib"): (12, 40, 40),
    ("Mega Drive", "Streets of Rage 2", "cib"): (30, 25, 15),
    ("Mega Drive", "Castlevania Bloodlines", "cib"): (110, 4, 2),
    ("Mega Drive", "console", "loose"): (40, 40, 30),
    ("Mega Drive", "console", "boxed"): (90, 12, 8),
    ("PS1", "Final Fantasy VII", "cib"): (35, 50, 40),
    ("PS1", "Final Fantasy VII", "loose"): (15, 40, 35),
    ("PS1", "Crash Bandicoot", "cib"): (15, 60, 60),
    ("PS1", "Resident Evil 2", "cib"): (30, 25, 15),
    ("PS1", "Silent Hill", "cib"): (85, 12, 6),
    ("PS1", "Suikoden II", "cib"): (260, 3, 1),
    ("PS1", "console", "loose"): (35, 40, 35),
    ("PS1", "console", "boxed"): (80, 10, 6),
    ("Game Boy", "Tetris", "loose"): (10, 70, 80),
    ("Game Boy", "Pokemon Red", "loose"): (45, 50, 30),
    ("Game Boy", "Pokemon Blue", "loose"): (45, 50, 30),
    ("Game Boy", "Zelda Link's Awakening", "loose"): (28, 30, 20),
    ("Game Boy", "console", "loose"): (40, 40, 25),
    ("Game Boy Color", "Pokemon Yellow", "loose"): (48, 40, 25),
    ("Game Boy Color", "Pokemon Crystal", "loose"): (75, 25, 12),
    ("Game Boy Color", "console", "loose"): (50, 35, 25),
    ("Game Boy Advance", "Pokemon Emerald", "loose"): (110, 30, 15),
    ("Game Boy Advance", "Pokemon FireRed", "loose"): (60, 30, 20),
    ("Game Boy Advance", "console", "loose"): (45, 40, 30),
    ("GameCube", "Mario Kart Double Dash", "cib"): (45, 35, 20),
    ("GameCube", "Super Smash Bros Melee", "cib"): (50, 30, 18),
    ("GameCube", "Luigi's Mansion", "cib"): (40, 25, 15),
    ("GameCube", "Metroid Prime", "cib"): (22, 30, 25),
    ("GameCube", "console", "loose"): (55, 35, 25),
    ("Dreamcast", "console", "loose"): (60, 30, 20),
    ("Dreamcast", "console", "boxed"): (120, 8, 5),
    ("Dreamcast", "Shenmue", "cib"): (30, 20, 15),
    ("Saturn", "Panzer Dragoon Saga", "cib"): (450, 2, 1),
    ("Saturn", "console", "loose"): (70, 15, 10),
    ("NES", "Super Mario Bros 3", "loose"): (20, 35, 30),
    ("NES", "console", "loose"): (45, 30, 20),
    ("DS", "console", "boxed"): (45, 40, 30),
    ("Master System", "console", "loose"): (30, 20, 15),
}


def _d(days_ago: int = 0, hours: int = 0) -> datetime:
    return datetime.utcnow() - timedelta(days=days_ago, hours=hours)


def _l(src: str, ext: str, title: str, price: float, *, desc: str = "", postage=None, coll=False, loc="", pc="",
       ltype="bin", ends_h=None, cond="", seller="", feedback=None, imgs=None) -> RawListing:
    urls = {
        "ebay": f"https://www.ebay.co.uk/itm/{ext}",
        "vinted": f"https://www.vinted.co.uk/items/{ext}",
        "facebook": f"https://www.facebook.com/marketplace/item/{ext}/",
        "gumtree": f"https://www.gumtree.com/p/video-games/x/{ext}",
        "shpock": f"https://www.shpock.com/en-gb/i/{ext}/",
        "depop": f"https://www.depop.com/products/{ext}/",
    }
    return RawListing(
        source=src, external_id=ext, url=urls[src], title=title, price=price, description=desc, postage_cost=postage,
        collection_only=coll, location_text=loc, postcode_district=pc, listing_type=ltype,
        ends_at=_d(hours=-ends_h) if ends_h else None, condition_text=cond, seller_name=seller, seller_feedback=feedback,
        image_urls=imgs or [f"https://img.example/{ext}.jpg"], raw={"seed": True},
    )


def seed_listings() -> list[RawListing]:
    """50 listings. Comments say what the pipeline *should* make of each."""
    L = _l
    return [
        # --- Good single-item deals (eBay) ---
        L("ebay", "395001", "Super Metroid SNES PAL cart only tested", 22, desc="Cart only, tested working, saves fine. Label good.", postage=2.5, cond="Used", seller="bob_retro", feedback=512),
        L("ebay", "395002", "Zelda A Link to the Past SNES Boxed complete with manual map", 48, desc="Complete in box with manual and map. Tested.", postage=3.5, cond="Used", seller="gamesgal", feedback=1200),
        L("ebay", "395003", "Conker's Bad Fur Day N64 PAL cartridge", 38, desc="Genuine Nintendo cart, tested on my console, label mint.", postage=0, cond="Used", seller="n64nick", feedback=88),
        L("ebay", "395004", "Pokemon Crystal Game Boy Color UK PAL - new save battery", 30, desc="Authentic cart, new battery fitted, saves. Label slightly faded.", postage=1.5, cond="Used", seller="pokecollect", feedback=3001),
        L("ebay", "395005", "Silent Hill PS1 PAL Black Label complete", 40, desc="Complete with manual, disc has light marks, plays fine.", postage=2.9, cond="Very Good", seller="horrorhits", feedback=40),
        L("ebay", "395006", "Mega Drive Castlevania Bloodlines boxed with manual PAL", 55, desc="Boxed with manual, tested. Rare!", postage=3.0, cond="Used", seller="sega_steve", feedback=650),
        L("ebay", "395007", "Nintendo 64 Console Boxed Complete Jungle Green with controller", 70, desc="Boxed Jungle Green N64, inserts, controller, leads. Tested.", postage=6.0, cond="Used", seller="attic_finds", feedback=15),
        L("ebay", "395008", "Pokemon Emerald GBA authentic UK cart tested saves", 60, desc="Genuine. Tested, saves. Checked PCB.", postage=1.5, cond="Used", seller="gba_guy", feedback=220),
        # --- Auctions ending soon ---
        L("ebay", "395009", "Super Nintendo SNES console bundle 2 controllers 4 games", 41, desc="Console, 2 pads, SMW, Street Fighter II Turbo, DKC, Mario All Stars. All tested.", postage=8.0, ltype="auction", ends_h=3, cond="Used", seller="clearout99", feedback=5),
        L("ebay", "395010", "Dreamcast console boxed with 2 controllers VMU Shenmue", 55, desc="Boxed Dreamcast, 2 pads, VMU, Shenmue. All working.", postage=7.0, ltype="auction", ends_h=6, cond="Used", seller="dc_dave", feedback=300),
        # --- Bad deals (fairly priced or overpriced) ---
        L("ebay", "395011", "Mario Kart 64 N64 PAL cart", 29, desc="Cart only, tested.", postage=2.5, cond="Used", seller="pricedright", feedback=900),
        L("ebay", "395012", "Sonic the Hedgehog 2 Mega Drive boxed", 14, desc="Boxed with manual.", postage=2.9, cond="Used", seller="sega_steve", feedback=650),
        L("ebay", "395013", "GoldenEye 007 N64 cartridge only", 19, desc="Tested working.", postage=2.5, cond="Used", seller="n64nick", feedback=88),
        L("ebay", "395014", "Final Fantasy VII PS1 PAL Platinum complete", 38, desc="Platinum version, complete, discs good.", postage=2.9, cond="Used", seller="ff_fan", feedback=200),
        L("ebay", "395015", "Game Boy Advance SP tribal edition + Pokemon FireRed", 150, desc="Rare tribal SP, with FireRed. Excellent condition.", postage=4.0, cond="Used", seller="collector_x", feedback=1500),
        # --- Fakes / repros / risky ---
        L("ebay", "395016", "Chrono Trigger SNES PAL cart - brand new", 25, desc="New cart, plays perfectly on PAL consoles. Custom label.", postage=2.5, cond="New", seller="cartworld_hk", feedback=12000),
        L("ebay", "395017", "Pokemon Emerald GBA cart", 15, desc="Works fine. No box.", postage=1.0, cond="Used", seller="newseller2024", feedback=0),
        L("ebay", "395018", "Suikoden II PS1 PAL complete", 60, desc="Complete. Image for illustration.", postage=3.0, cond="Used", seller="quickflip", feedback=3, imgs=["https://img.example/stock_suikoden.jpg"]),
        L("ebay", "395019", "Super Metroid SNES untested spares or repair", 20, desc="Found in loft, untested, sold as seen.", postage=2.5, cond="For parts or not working", seller="loftclear", feedback=20),
        L("ebay", "395020", "Panzer Dragoon Saga Sega Saturn NTSC-J Japanese complete", 60, desc="Japanese version, complete, spine card.", postage=4.0, cond="Used", seller="jp_imports", feedback=8000),
        # --- Bundles / job lots ---
        L("ebay", "395021", "Retro games job lot - 12 x N64 games Mario Kart GoldenEye Ocarina Banjo", 95, desc="12 N64 games: Mario Kart 64, GoldenEye 007, Zelda Ocarina of Time, Banjo-Kazooie, Super Mario 64 and 7 sports titles. All tested.", postage=6.0, cond="Used", seller="bundle_bill", feedback=70),
        L("ebay", "395022", "PS1 games bundle x10 Crash Resident Evil 2 FF7", 45, desc="Crash Bandicoot, Resident Evil 2, Final Fantasy VII, plus 7 others. Some cracked cases.", postage=5.0, cond="Used", seller="ps1pete", feedback=340),
        L("ebay", "395023", "Game Boy collection Tetris Pokemon Red Pokemon Blue Zelda Link's Awakening", 90, desc="4 carts, all tested, Pokemon games save.", postage=2.5, cond="Used", seller="gb_gina", feedback=410),
        # --- Vinted (posted, buyer protection) ---
        L("vinted", "4471234567", "Super Mario World SNES PAL boxed", 22, desc="Boxed with manual, tested.", postage=2.99, loc="Leeds", seller="retro_jo"),
        L("vinted", "4471234999", "SNES console bundle 2 pads 3 games tested", 60, desc="SNES, 2 pads, SMW, DKC, Street Fighter II Turbo.", postage=5.49, loc="Bristol", seller="clearout"),
        L("vinted", "4471235555", "Chrono Trigger SNES cart repro", 18.5, desc="Reproduction cart, works on PAL.", postage=2.99, loc="London", seller="cartman"),
        L("vinted", "4471236001", "Zelda Ocarina of Time N64 complete boxed", 42, desc="Boxed, manual, tested, saves.", postage=3.49, loc="Glasgow", seller="zelda_z"),
        L("vinted", "4471236002", "Tetris Game Boy cart", 9, desc="Cart only.", postage=1.99, loc="Hull", seller="gb_fan"),
        L("vinted", "4471236003", "Pokemon Red Game Boy UK genuine tested saves", 26, desc="Saves fine, new battery.", postage=1.99, loc="Norwich", seller="pokebox"),
        L("vinted", "4471236004", "Metroid Prime GameCube complete", 24, desc="Complete, disc mint.", postage=2.99, loc="Derby", seller="cube"),
        # --- Facebook Marketplace (collection only, varying distance from Manchester base) ---
        L("facebook", "1234567890123", "Nintendo 64 console with 2 controllers and Mario Kart 64", 40, desc="N64, 2 official pads, Mario Kart 64. Works. Collection Stockport.", coll=True, loc="Stockport, Greater Manchester", pc="SK4", seller="Dave"),
        L("facebook", "1234567890456", "Job lot of PS1 games x9 untested", 15, desc="9 PS1 games, untested, found in garage.", coll=True, loc="Bolton, Greater Manchester", pc="BL1", seller="Sam"),
        L("facebook", "1234567890789", "Sega Mega Drive 2 boxed with Sonic 2 and Streets of Rage 2", 45, desc="Boxed MD2, Sonic 2 boxed, SoR2 boxed, one pad. Tested.", coll=True, loc="Sheffield, South Yorkshire", pc="S1", seller="Gaz"),
        L("facebook", "1234567891000", "SNES console boxed with Super Mario World", 50, desc="Boxed SNES with SMW, 1 pad, leads. Works.", coll=True, loc="Plymouth, Devon", pc="PL1", seller="Jo"),
        L("facebook", "1234567891001", "Game Boy Color purple + 3 games", 25, desc="GBC purple, Pokemon Yellow, Tetris DX, Mario Golf.", coll=True, loc="Salford", pc="M5", seller="Ash"),
        L("facebook", "1234567891002", "PS1 console with 2 pads memory card and 6 games", 20, desc="Works, Crash Bandicoot, FF7 (scratched), Tekken 3 etc.", coll=True, loc="Oldham", pc="OL1", seller="Mo"),
        L("facebook", "1234567891003", "Original xbox and ps2 bundle need gone tonight no questions asked", 30, desc="Need gone tonight, cash only, no questions asked.", coll=True, loc="Manchester", pc="M4", seller="Lee"),
        L("facebook", "1234567891004", "Nintendo DS Lite boxed", 20, desc="Boxed, charger, works.", coll=True, loc="Wigan", pc="WN1", seller="Beth"),
        # --- Gumtree ---
        L("gumtree", "1489912345", "GameCube console boxed with 4 games", 70, desc="Purple GameCube boxed, pad, memory card, Mario Kart Double Dash, Smash Bros Melee, Luigi's Mansion, Mario Sunshine. Collection only.", coll=True, loc="Macclesfield, Cheshire", pc="SK10", seller="Steve"),
        L("gumtree", "1489923456", "Sega Dreamcast with controller + VMU, spares or repair", 25, desc="Doesn't read discs. Spares or repair.", coll=True, loc="Liverpool", pc="L1", seller="Tom"),
        L("gumtree", "1489934567", "Retro games job lot SNES Mega Drive 14 games", 90, desc="SNES: Super Mario World, Donkey Kong Country, Street Fighter II Turbo, Super Metroid. Mega Drive: Sonic 2, Streets of Rage 2 boxed + 8 others. Can post.", coll=False, postage=8.0, loc="Preston", pc="PR1", seller="Nina"),
        L("gumtree", "1489945678", "Sega Saturn console with 2 pads", 45, desc="Works, 2 pads, leads. Collection Birmingham.", coll=True, loc="Birmingham", pc="B1", seller="Raj"),
        # --- Shpock ---
        L("shpock", "ZtB1xAbCdEf", "Game Boy Color purple with Pokemon Yellow", 45, desc="Works, Pokemon Yellow saves. Can post +£3.50", postage=3.5, loc="Warrington", pc="WA1", seller="Kelly"),
        L("shpock", "ZtB2yGhIjKl", "PS1 Final Fantasy VII PAL complete", 30, desc="Complete, black label, discs good.", postage=3.0, loc="Wigan", pc="WN1", seller="Chris"),
        L("shpock", "ZtB3zMnOpQr", "Nintendo NES console with Super Mario Bros 3", 55, desc="NES, 1 pad, SMB3. Tested.", postage=7.0, loc="Chester", pc="CH1", seller="Pat"),
        # --- Depop ---
        L("depop", "retrokid-nintendo-ds-lite-pink-boxed", "Nintendo DS Lite pink boxed with charger", 35, desc="Boxed, works. Free postage.", postage=0, loc="London", seller="retrokid"),
        L("depop", "pixelpete-n64-goldeneye-cart", "N64 GoldenEye 007 cart PAL tested", 12, desc="Tested. +£3.50 shipping", postage=3.5, loc="Cardiff", seller="pixelpete"),
        # --- More eBay: edge cases ---
        L("ebay", "395024", "Nintendo Game Boy DMG-01 original grey console working", 28, desc="Screen has 2 vertical lines, otherwise works. Battery cover present.", postage=3.0, cond="Used", seller="dmg_dan", feedback=55),
        L("ebay", "395025", "Super Mario World SNES - NTSC US import cart", 9, desc="US version, needs converter or modded console.", postage=2.5, cond="Used", seller="us_imports", feedback=950),
        L("ebay", "395026", "Sega Master System II console with built in Alex Kidd", 18, desc="Works, 1 pad, RF lead.", postage=5.0, cond="Used", seller="sms_sue", feedback=130),
    ]


def seed_sold_comps(days: int = 90, seed: int = 42) -> list[dict]:
    """Generate plausible sold comps from MARKET (deterministic)."""
    rng = random.Random(seed)
    out = []
    for (platform, title, completeness), (median, n_sold, _active) in MARKET.items():
        for i in range(n_sold):
            price = max(1.0, rng.gauss(median, median * 0.18))
            out.append({
                "provider": "mock", "platform": platform, "title": title, "region": "PAL" if "NTSC" not in title else "NTSC-J",
                "completeness": completeness, "sold_price": round(price, 2), "postage": round(rng.choice([0, 1.55, 2.5, 3.35]), 2),
                "sold_at": datetime.utcnow() - timedelta(days=rng.uniform(0, days)), "external_id": f"mock-{platform}-{title}-{completeness}-{i}",
            })
    return out


def active_count_for(platform: str, title: str, completeness: str) -> int:
    hit = MARKET.get((platform, title, completeness))
    if hit:
        return hit[2]
    for (p, t, _c), (_m, _n, a) in MARKET.items():
        if p == platform and t == title:
            return a
    return 20


def seed_demo_history(db, niche, deals: list) -> int:
    """Mock-mode only: backdate a handful of bought->sold items so the P&L, accuracy and insights pages have data."""
    from datetime import date
    from app.inventory.service import mark_bought, record_sale, set_status
    from app.settings_store import get_setting, set_setting

    if get_setting(db, "demo_history_loaded", False):
        return 0
    rng = random.Random(7)
    candidates = [d for d in deals if 5 < d.net_profit and d.net_margin < 0.5
                  and not any(f["code"] in ("repro", "too_good", "stolen_signals") for f in d.item.risk_flags)]
    # Prefer the near-miss deals so the alerted ones stay open in the demo feed
    candidates.sort(key=lambda d: (d.should_alert, -d.score))
    n = 0
    for i, d in enumerate(candidates[:12]):
        if d.status != "new":
            continue
        inv = mark_bought(db, d)
        days_ago = 60 - i * 8
        inv.purchase_date = date.today() - timedelta(days=days_ago)
        inv.listed_at = datetime.utcnow() - timedelta(days=days_ago - 3)
        set_status(db, inv, "listed")
        if i < 4:
            sold_after = max(2, int(d.est_days_to_sell * rng.uniform(0.6, 1.5)))
            sold_at = inv.listed_at + timedelta(days=sold_after)
            if sold_at < datetime.utcnow():
                price = round(d.expected_sale_price * rng.uniform(0.9, 1.12), 2)
                fees = round(price * 0.131 + 0.3, 2)
                record_sale(db, inv, "ebay", price, fees, postage_cost=d.outbound_postage, packaging_cost=d.packaging, sold_at=sold_at)
                if i % 3 == 0:
                    inv.status = "shipped"
        n += 1
    set_setting(db, "demo_history_loaded", True)
    db.flush()
    return n
