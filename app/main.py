"""FastAPI application factory. `uvicorn app.main:app` or `python -m app.main`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, db_session
from app.logging_config import setup_logging

log = logging.getLogger(__name__)


def bootstrap(load_seed: bool | None = None) -> None:
    """Create tables (dev/sqlite), seed defaults, sync niches, opening balance, mock seed data."""
    from app.analytics.pnl import ensure_opening_balance
    from app.models import Deal, RawListing
    from app.niches.loader import sync_niches
    from app.settings_store import seed_defaults

    s = get_settings()
    create_all()
    with db_session() as db:
        seed_defaults(db)
        niches = sync_niches(db)
        ensure_opening_balance(db)
        want_seed = s.mock_mode if load_seed is None else load_seed
        if want_seed and niches and db.scalar(select(RawListing.id).limit(1)) is None:
            from app.pipeline import load_seed_listings
            from app.seed import seed_demo_history
            deals = load_seed_listings(db, niches[0], notify=True)
            n = seed_demo_history(db, niches[0], deals)
            log.info("seeded %s listings -> %s deals (%s alerts), %s demo stock items", len(deals), len(deals),
                     sum(d.should_alert for d in deals), n)
        elif want_seed and niches:
            from app.identification.valuation import seed_mock_comps
            seed_mock_comps(db, niches[0])
        db.query(Deal).count()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.log_level)
    bootstrap()
    from app.jobs.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    log.info("DealFinder up: mock_mode=%s llm=%s notifier=%s db=%s", s.mock_mode, "mock" if s.llm_is_mock else s.claude_model,
             s.notifier, s.database_url.split("@")[-1])
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    from app.web.routes import analytics, dashboard, deals, inventory, settings as settings_routes

    app = FastAPI(title="DealFinder", lifespan=lifespan)
    static = Path(__file__).parent / "web" / "static"
    static.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static)), name="static")
    for r in (dashboard.router, deals.router, inventory.router, analytics.router, settings_routes.router):
        app.include_router(r)
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
