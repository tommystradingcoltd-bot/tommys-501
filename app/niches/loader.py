"""Load niche configs from YAML and sync them into the niches table."""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Niche, SearchQuery

NICHE_DIR = Path(__file__).parent


def load_niche_files() -> list[dict]:
    out = []
    for p in sorted(NICHE_DIR.glob("*.yaml")):
        with p.open() as fh:
            data = yaml.safe_load(fh)
        if data and data.get("slug"):
            out.append(data)
    return out


def sync_niches(db: Session) -> list[Niche]:
    """Create niches in the DB from YAML files (never overwrites a config edited in the dashboard)."""
    niches = []
    for data in load_niche_files():
        niche = db.scalar(select(Niche).where(Niche.slug == data["slug"]))
        if niche is None:
            niche = Niche(slug=data["slug"], name=data["name"], active=data.get("active", True), config=data)
            db.add(niche)
            db.flush()
            for term in data.get("search_terms", []):
                db.add(SearchQuery(niche_id=niche.id, query=term, filters=dict(data.get("default_filters", {}))))
        niches.append(niche)
    db.flush()
    return niches


def niche_config(niche: Niche) -> dict:
    return niche.config or {}
