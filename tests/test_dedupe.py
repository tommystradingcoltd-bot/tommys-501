from app.sourcing.dedupe import find_duplicate, hamming, is_cross_post
from app.sourcing.runner import persist_listing
from app.seed import seed_listings
from app.sourcing.base import RawListing


def test_cross_post_detection():
    assert is_cross_post("Super Mario World SNES PAL boxed", 22, "", "SNES Super Mario World boxed PAL", 22.5, "")
    assert not is_cross_post("Super Mario World SNES PAL boxed", 22, "", "Super Metroid SNES", 22, "")
    assert not is_cross_post("Super Mario World SNES PAL boxed", 22, "", "Super Mario World SNES PAL boxed", 40, "")
    assert is_cross_post("Super Mario World SNES", 22, "ff00ff00ff00ff00", "Super Mario World SNES boxed PAL", 29, "ff00ff00ff00ff01")
    assert hamming("ff00", "ff01") == 1


def test_persist_dedupes_by_source_and_id_and_cross_posts(db, niche):
    from sqlalchemy import select
    from app.models import Source
    sources = {s.slug: s for s in db.scalars(select(Source))}
    rl = seed_listings()[0]
    row, new = persist_listing(db, sources["ebay"], niche, rl)
    row2, new2 = persist_listing(db, sources["ebay"], niche, rl)
    assert new and not new2 and row.id == row2.id
    cross = RawListing(source="vinted", external_id="x1", url="https://v/x1", title=rl.title, price=rl.price)
    row3, new3 = persist_listing(db, sources["vinted"], niche, cross)
    assert new3 and row3.status == "duplicate" and row3.duplicate_of_id == row.id
    assert find_duplicate(db, row3).id == row.id
