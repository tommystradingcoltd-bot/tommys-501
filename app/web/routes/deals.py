"""Deals feed + deal detail + decisions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.inventory.service import mark_bought
from app.models import Deal, RawListing, Source
from app.web import templates

router = APIRouter(prefix="/deals")
SORTS = {"score": Deal.score.desc(), "margin": Deal.net_margin.desc(), "profit": Deal.net_profit.desc(),
         "speed": Deal.est_days_to_sell.asc(), "distance": Deal.distance_miles.asc(), "newest": Deal.created_at.desc()}


@router.get("", response_class=HTMLResponse)
def deals_feed(request: Request, db: Session = Depends(get_db), sort: str = "score", source: str = "", status: str = "open",
               min_margin: float = 0.0, max_days: int = 0, max_distance: float = 0, show_all: int = 0):
    q = select(Deal).join(RawListing, Deal.raw_listing_id == RawListing.id)
    if status == "open":
        q = q.where(Deal.status.in_(["new", "alerted", "watching"]))
    elif status != "all":
        q = q.where(Deal.status == status)
    if not show_all and status in ("open",):
        q = q.where(Deal.should_alert == True)  # noqa: E712
    if source:
        q = q.join(Source, RawListing.source_id == Source.id).where(Source.slug == source)
    if min_margin:
        q = q.where(Deal.net_margin >= min_margin / 100)
    if max_days:
        q = q.where(Deal.est_days_to_sell <= max_days)
    if max_distance:
        q = q.where((Deal.distance_miles <= max_distance) | (Deal.distance_miles.is_(None)))
    q = q.order_by(SORTS.get(sort, SORTS["score"])).limit(200)
    deals = db.scalars(q).all()
    sources = db.scalars(select(Source).order_by(Source.name)).all()
    return templates.TemplateResponse(request, "deals.html", {"deals": deals, "sources": sources, "sort": sort, "source": source,
                                                              "status": status, "min_margin": min_margin, "max_days": max_days,
                                                              "max_distance": max_distance, "show_all": show_all})


@router.get("/{deal_id}", response_class=HTMLResponse)
def deal_detail(deal_id: int, request: Request, db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if not deal:
        return RedirectResponse("/deals", status_code=303)
    return templates.TemplateResponse(request, "deal_detail.html", {"deal": deal, "item": deal.item, "listing": deal.raw_listing, "b": deal.breakdown or {}})


@router.post("/{deal_id}/decide")
def decide(deal_id: int, request: Request, action: str = Form(...), actual_price: Optional[str] = Form(None), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if not deal:
        return RedirectResponse("/deals", status_code=303)
    if action == "bought":
        price = float(actual_price) if actual_price else None
        inv = mark_bought(db, deal, price)
        return RedirectResponse(f"/inventory/{inv.id}", status_code=303)
    if action in ("pass", "watch", "reopen"):
        deal.status = {"pass": "passed", "watch": "watching", "reopen": "new"}[action]
        deal.decided_at = datetime.utcnow()
    nxt = request.headers.get("referer") or "/deals"
    return RedirectResponse(nxt, status_code=303)
