"""P&L, projections, insights, sold-data upload."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.insights import generate_weekly_insights
from app.analytics.pnl import accuracy, avg_days_to_sell, cash_available, learned_uplift, monthly_margins, pnl_by, stock_value_at_cost
from app.analytics.projections import ProjectionInputs, project
from app.db import get_db
from app.identification.valuation import CsvImportProvider
from app.models import Insight, Niche, SoldComp
from app.settings_store import get_setting, set_setting
from app.web import templates

router = APIRouter()


@router.get("/pnl", response_class=HTMLResponse)
def pnl(request: Request, db: Session = Depends(get_db), months: int = 6):
    return templates.TemplateResponse(request, "pnl.html", {
        "by_item": pnl_by(db, "item", months), "by_month": pnl_by(db, "month", months), "by_source": pnl_by(db, "source", months),
        "by_platform": pnl_by(db, "platform", months), "accuracy": accuracy(db, months), "months": months,
        "uplift": learned_uplift(db), "current_uplift": get_setting(db, "listing_quality_uplift", 0.0),
    })


@router.post("/pnl/apply-uplift")
def apply_uplift(db: Session = Depends(get_db)):
    u = learned_uplift(db)
    if u is not None:
        set_setting(db, "listing_quality_uplift", max(-0.3, min(0.3, u)))
    return RedirectResponse("/pnl", status_code=303)


@router.get("/projections", response_class=HTMLResponse)
def projections(request: Request, db: Session = Depends(get_db), margin: float = 0, days: float = 0):
    monthly = [m for m in monthly_margins(db, 3) if m["sales"]]
    realised_margin = sum(m["margin"] for m in monthly) / len(monthly) if monthly else 0.30
    realised_days = avg_days_to_sell(db) or 30.0
    inp = ProjectionInputs(
        starting_capital=float(get_setting(db, "starting_capital", 5000)), current_capital=cash_available(db) + stock_value_at_cost(db),
        net_margin=(margin / 100) if margin else realised_margin, avg_days_to_sell=days or realised_days,
        monthly_buying_capacity=float(get_setting(db, "monthly_buying_capacity", 4000)),
    )
    return templates.TemplateResponse(request, "projections.html", {"p": project(inp), "inp": inp, "monthly": monthly})


@router.get("/insights", response_class=HTMLResponse)
def insights(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Insight).order_by(Insight.created_at.desc()).limit(8)).all()
    return templates.TemplateResponse(request, "insights.html", {"insights": rows})


@router.post("/insights/generate")
def insights_generate(db: Session = Depends(get_db)):
    generate_weekly_insights(db)
    return RedirectResponse("/insights", status_code=303)


@router.get("/sold-data", response_class=HTMLResponse)
def sold_data(request: Request, db: Session = Depends(get_db)):
    counts = db.execute(select(SoldComp.provider, func.count(SoldComp.id)).group_by(SoldComp.provider)).all()
    niches = db.scalars(select(Niche)).all()
    return templates.TemplateResponse(request, "sold_data.html", {"counts": counts, "niches": niches, "msg": request.query_params.get("msg", "")})


@router.post("/sold-data/upload")
async def sold_upload(niche_id: int = Form(...), default_platform: str = Form(""), file: UploadFile = File(...), db: Session = Depends(get_db)):
    niche = db.get(Niche, niche_id)
    content = (await file.read()).decode("utf-8", errors="ignore")
    n = CsvImportProvider.import_csv(db, niche, content, default_platform) if niche else 0
    return RedirectResponse(f"/sold-data?msg=Imported+{n}+sold+comps", status_code=303)
