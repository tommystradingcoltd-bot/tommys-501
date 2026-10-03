import yaml
from pathlib import Path

from app.identification.normaliser import item_key, rule_based_normalise
from app.identification.risk import rule_based_flags

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "app" / "niches" / "retro_games.yaml").read_text())


def norm(title, desc=""):
    return rule_based_normalise(title, desc, CFG)


def test_platform_title_completeness_region():
    r = norm("Super Metroid SNES PAL cart only tested")
    assert (r["platform"], r["title"], r["completeness"], r["region"], r["category"]) == ("SNES", "Super Metroid", "loose", "PAL", "game")
    r = norm("Zelda Ocarina of Time N64 complete boxed", "Boxed, manual.")
    assert r["completeness"] == "cib" and r["platform"] == "N64"
    r = norm("Super Mario World SNES - NTSC US import cart")
    assert r["region"] == "NTSC-U"
    r = norm("Panzer Dragoon Saga Sega Saturn NTSC-J Japanese complete")
    assert r["region"] == "NTSC-J" and r["platform"] == "Saturn"


def test_longest_platform_alias_wins():
    assert norm("Pokemon Crystal Game Boy Color UK")["platform"] == "Game Boy Color"
    assert norm("Pokemon Emerald GBA cart")["platform"] == "Game Boy Advance"
    assert norm("Tetris Game Boy cart")["platform"] == "Game Boy"


def test_bundles_list_items():
    r = norm("Retro games job lot - 12 x N64 games Mario Kart GoldenEye Ocarina Banjo", "Mario Kart 64, GoldenEye 007, Zelda Ocarina of Time, Banjo-Kazooie, Super Mario 64")
    assert r["is_bundle"] and r["category"] == "bundle"
    titles = {b["title"] for b in r["bundle_items"]}
    assert {"Mario Kart 64", "GoldenEye 007", "Zelda Ocarina of Time", "Banjo-Kazooie", "Super Mario 64"} <= titles
    r = norm("Nintendo 64 console with 2 controllers and Mario Kart 64")
    assert r["is_bundle"] and {b["title"] for b in r["bundle_items"]} == {"console", "Mario Kart 64"}
    r = norm("Job lot of PS1 games x9 untested")
    assert r["is_bundle"] and r["confidence"] < 0.5


def test_consoles():
    r = norm("Sega Dreamcast with controller + VMU, spares or repair")
    assert r["category"] == "console" and r["platform"] == "Dreamcast"
    r = norm("Nintendo 64 Console Boxed Complete Jungle Green with controller")
    assert r["category"] == "console" and r["completeness"] == "boxed" and "jungle green" in r["console_model"]


def test_item_key_stable_and_case_insensitive():
    assert item_key("retro_games", "SNES", "Super Metroid", "PAL", "loose") == item_key("retro_games", "snes", "super metroid", "pal", "LOOSE")
    assert item_key("retro_games", "SNES", "Super Metroid", "PAL", "loose") != item_key("retro_games", "SNES", "Super Metroid", "PAL", "cib")


def flags(title, desc="", **kw):
    v = {"title": title, "description": desc, "condition": kw.get("condition", ""), "niche_config": CFG, "price": kw.get("price", 20),
         "median": kw.get("median"), "normalised": kw.get("normalised", {"category": "game", "platform": "SNES", "region": "PAL"}),
         "seller_feedback": kw.get("feedback"), "source": kw.get("source", "ebay")}
    return {f["code"]: f for f in rule_based_flags(v)}


def test_risk_flags():
    assert "repro" in flags("Chrono Trigger SNES cart repro")
    assert flags("Chrono Trigger SNES PAL cart", "Custom label", condition="New")["repro"]["severity"] == "high"
    assert "too_good" in flags("Chrono Trigger SNES", price=25, median=380)
    assert "too_good" not in flags("Chrono Trigger SNES", price=300, median=380)
    assert "untested" in flags("Super Metroid", "untested, sold as seen")
    assert "faulty" in flags("Dreamcast", "spares or repair")
    assert "stolen_signals" in flags("xbox bundle", "need gone tonight no questions asked")
    assert "stock_photo" in flags("Suikoden II", "Image for illustration")
    assert "missing_manual" in flags("Zelda", "no manual")
    assert "new_seller" in flags("Game", feedback=0)
    assert "region_mismatch" in flags("Super Mario World PAL", normalised={"category": "game", "platform": "SNES", "region": "NTSC-U"})
    assert not flags("Super Metroid SNES PAL cart only tested", "Cart only, tested working, saves fine.", feedback=500)
