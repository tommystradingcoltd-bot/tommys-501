import os

os.environ.update({"APP_ENV": "test", "MOCK_MODE": "true", "SCHEDULER_ENABLED": "false", "NOTIFIER": "mock",
                   "ANTHROPIC_API_KEY": "", "EBAY_CLIENT_ID": "", "DASHBOARD_BASE_URL": "http://test"})

import pytest  # noqa: E402

from app.db import configure_engine, create_all, session_factory  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    configure_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_all()
    from app.analytics.pnl import ensure_opening_balance
    from app.identification.llm import MockLLMClient, set_llm
    from app.inventory.ebay_sell import MockEbaySellClient, set_ebay_sell
    from app.niches.loader import sync_niches
    from app.notify.mock import MockNotifier
    from app.notify.service import set_notifier
    from app.settings_store import seed_defaults
    set_llm(MockLLMClient())
    set_notifier(MockNotifier())
    set_ebay_sell(MockEbaySellClient())
    s = session_factory()()
    seed_defaults(s)
    sync_niches(s)
    ensure_opening_balance(s)
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def niche(db):
    from sqlalchemy import select
    from app.models import Niche
    return db.scalar(select(Niche).where(Niche.slug == "retro_games"))


@pytest.fixture()
def notifier():
    from app.notify.service import get_notifier
    return get_notifier()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
