from app.profit.distance import collection_cost, geocode, road_miles

BASE = {"postcode": "M1", "lat": 53.4794, "lon": -2.2453}


def test_geocode_postcode_and_town():
    assert geocode("SK4") == (53.41, -2.16)
    assert geocode("", "Stockport, Greater Manchester") == (53.41, -2.16)   # earliest town wins
    assert geocode("", "Collection from Plymouth PL1") == (50.38, -4.14)
    assert geocode("ZZ9", "nowhere") is None


def test_road_miles_scale():
    near = road_miles(BASE, "SK4")
    far = road_miles(BASE, "PL1")
    assert near is not None and far is not None and 3 < near < 15 and 250 < far < 320
    assert road_miles(BASE, "", "") is None
    assert road_miles({"postcode": "M1"}, "", "Bolton") is not None  # base resolved from postcode


def test_collection_cost_components():
    assert collection_cost(10, 45, 12, 30, 20) == round(20 * 0.45 + (20 / 30 + 20 / 60) * 12, 2)
