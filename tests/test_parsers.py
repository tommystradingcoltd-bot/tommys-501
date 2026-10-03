from pathlib import Path

import pytest

from app.sourcing.browser import parser
from app.sourcing.browser.helper import BROWSER_SITES, FixtureBrowserWatcher
from app.sourcing.base import SourcePaused

FX = Path(__file__).parent / "fixtures" / "html"


@pytest.mark.parametrize("site", BROWSER_SITES)
def test_search_fixture_parses(site):
    res = parser.parse_search_results(site, (FX / f"{site}_search.html").read_text())
    assert len(res) >= 2
    for r in res:
        assert r.title and r.price > 0 and r.url.startswith("http") and r.external_id
        assert r.source == site


@pytest.mark.parametrize("site", BROWSER_SITES)
def test_detail_fixture_parses(site):
    url = parser.parse_search_results(site, (FX / f"{site}_search.html").read_text())[0].url
    d = parser.parse_detail(site, (FX / f"{site}_detail.html").read_text(), url)
    assert d.title and d.price > 0 and d.description


def test_facebook_results_are_collection_with_location():
    res = parser.parse_search_results("facebook", (FX / "facebook_search.html").read_text())
    assert all(r.collection_only for r in res)
    assert res[0].location_text.startswith("Stockport")


def test_gumtree_detail_records_postcode_district_and_collection():
    d = parser.parse_detail("gumtree", (FX / "gumtree_detail.html").read_text(), "https://www.gumtree.com/p/x/1489912345")
    assert d.postcode_district == "SK10" and d.collection_only


def test_shpock_detail_postage_from_text():
    d = parser.parse_detail("shpock", (FX / "shpock_detail.html").read_text(), "https://www.shpock.com/en-gb/i/ZtB1xAbCdEf/")
    assert d.postage_cost == 3.5 and not d.collection_only


def test_block_detection():
    assert parser.detect_block("vinted", (FX / "vinted_login_wall.html").read_text())[0] == "needs_login"
    assert parser.detect_block("facebook", (FX / "facebook_login_wall.html").read_text())[0] == "needs_login"
    assert parser.detect_block("gumtree", (FX / "gumtree_captcha.html").read_text())[0] == "paused"
    assert parser.detect_block("gumtree", (FX / "gumtree_search.html").read_text()) is None


def test_price_and_postcode_helpers():
    assert parser.parse_price("£1,234.50") == 1234.5
    assert parser.parse_price("£45") == 45.0
    assert parser.parse_price("Free") is None
    assert parser.extract_postcode_district("Collection from Macclesfield SK10 2AB") == "SK10"
    assert parser.extract_postcode_district("Leeds") == ""


def test_fixture_watcher_raises_paused_on_login_wall():
    w = FixtureBrowserWatcher("vinted", (FX / "vinted_login_wall.html").read_text())
    with pytest.raises(SourcePaused) as e:
        w.search("snes", {})
    assert e.value.status == "needs_login"


def test_fixture_watcher_applies_max_price():
    w = FixtureBrowserWatcher("vinted", (FX / "vinted_search.html").read_text())
    assert len(w.search("snes", {"max_price": 30})) == 2
    assert w.build_search_url("snes games", {"max_price": 50}).startswith("https://www.vinted.co.uk/catalog?search_text=snes+games")
