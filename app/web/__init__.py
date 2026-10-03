"""Jinja environment + template filters shared by all routes."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if v < 0 else ""
    return f"{sign}£{abs(v):,.2f}"


def pct(v, digits: int = 0) -> str:
    try:
        return f"{float(v) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def dt(v, fmt: str = "%d %b %H:%M") -> str:
    if not v:
        return "-"
    if isinstance(v, (datetime, date)):
        return v.strftime(fmt)
    return str(v)


def ago(v) -> str:
    if not v:
        return "never"
    delta = datetime.utcnow() - v
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


templates.env.filters.update({"money": money, "pct": pct, "dt": dt, "ago": ago})
templates.env.globals.update({"now": datetime.utcnow, "statuses": ["in_transit", "testing", "ready_to_photograph", "listed", "sold", "shipped", "returned"]})
