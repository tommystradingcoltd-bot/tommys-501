"""Inventory kanban, item detail, testing, listings, sales, labels, CSV export."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.inventory.crosslist import listings_csv
from app.inventory.labels import label_pdf
from app.inventory.listing_gen import generate_listing
from app.inventory.service import add_platform_listing, list_on_ebay, mark_platform_removed, mark_shipped, record_sale, set_status
from app.inventory.testing import checklist_for, record_test
from app.models import INVENTORY_STATUSES, InventoryItem, Listing, Niche, PlatformListing
from app.web import templates

router = APIRouter(prefix="/inventory")


@router.get("", response_class=HTMLResponse)
def board(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(InventoryItem).order_by(InventoryItem.updated_at.desc())).all()
    columns = {s: [i for i in items if i.status == s] for s in INVENTORY_STATUSES}
    return templates.TemplateResponse(request, "inventory.html", {"columns": columns, "total": len(items)})


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    listings = db.scalars(select(Listing).where(Listing.status.in_(["draft", "active"]))).all()
    return PlainTextResponse(listings_csv(listings), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=listings.csv"})


@router.get("/{item_id}", response_class=HTMLResponse)
def item_detail(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if not item:
        return RedirectResponse("/inventory", status_code=303)
    niche = db.get(Niche, item.niche_id)
    latest = max(item.test_results, key=lambda t: t.tested_at) if item.test_results else None
    checklist = latest.checklist if latest else checklist_for(niche, item.category)
    listing = max(item.listings, key=lambda l: l.created_at) if item.listings else None
    return templates.TemplateResponse(request, "item_detail.html", {"item": item, "checklist": checklist, "latest_test": latest,
                                                                    "listing": listing, "sale": item.sales[0] if item.sales else None})


@router.post("/{item_id}/status")
def change_status(item_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if item:
        if status == "shipped":
            mark_shipped(db, item)
        else:
            set_status(db, item, status)
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/test")
async def save_test(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    form = await request.form()
    results = {k[7:]: v for k, v in form.items() if k.startswith("result_")}
    notes = {k[6:]: v for k, v in form.items() if k.startswith("notes_")}
    if item:
        record_test(db, item, results, notes, grade=form.get("grade", ""), summary=form.get("summary", ""))
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/listing")
def make_listing(item_id: int, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if item:
        generate_listing(db, item)
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/listing/{listing_id}/update")
def update_listing(item_id: int, listing_id: int, title: str = Form(...), price: float = Form(...), description: str = Form(""),
                   db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if l:
        l.title, l.price, l.description = title[:80], price, description
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/listing/{listing_id}/publish")
def publish(item_id: int, listing_id: int, platform: str = Form("ebay"), external_id: str = Form(""), url: str = Form(""),
            db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if l:
        if platform == "ebay":
            list_on_ebay(db, l)
        else:
            add_platform_listing(db, l, platform, external_id, url)
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/platform/{pl_id}/removed")
def platform_removed(item_id: int, pl_id: int, db: Session = Depends(get_db)):
    pl = db.get(PlatformListing, pl_id)
    if pl:
        mark_platform_removed(db, pl)
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.post("/{item_id}/sale")
def sale(item_id: int, platform: str = Form("ebay"), sale_price: float = Form(...), platform_fees: float = Form(0.0),
         payment_fees: float = Form(0.0), postage_cost: float = Form(0.0), packaging_cost: float = Form(0.0),
         postage_charged: float = Form(0.0), other_costs: float = Form(0.0), external_order_id: str = Form(""),
         sold_at: Optional[str] = Form(None), db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if item:
        when = datetime.fromisoformat(sold_at) if sold_at else None
        record_sale(db, item, platform, sale_price, platform_fees, payment_fees, postage_cost, packaging_cost, postage_charged,
                    other_costs, external_order_id, when)
    return RedirectResponse(f"/inventory/{item_id}", status_code=303)


@router.get("/{item_id}/label.pdf")
def label(item_id: int, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if not item:
        return RedirectResponse("/inventory", status_code=303)
    return Response(label_pdf([item]), media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={item.sku}.pdf"})
