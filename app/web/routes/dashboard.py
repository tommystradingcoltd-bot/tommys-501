"""Home, health, tasks."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.pnl import avg_days_to_sell, cash_available, deal_stats_today, month_bounds, realised_profit, stock_value_at_cost
from app.db import get_db
from app.models import Alert, Deal, InventoryItem, Source, Task
from app.web import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    start, end = month_bounds(date.today())
    today_start = datetime.combine(date.today(), datetime.min.time())
    deals = db.scalars(select(Deal).where(Deal.should_alert == True, Deal.status.in_(["new", "alerted", "watching"]))  # noqa: E712
                       .order_by(Deal.score.desc()).limit(8)).all()
    overdue = [i for i in db.scalars(select(InventoryItem).where(InventoryItem.status == "listed")) if i.is_overdue]
    tasks = db.scalars(select(Task).where(Task.done == False).order_by(Task.urgent.desc(), Task.created_at.desc()).limit(8)).all()  # noqa: E712
    sources = db.scalars(select(Source).where(Source.enabled == True)).all()  # noqa: E712
    attention = [s for s in sources if s.status in ("needs_login", "blocked", "paused", "error")]
    return templates.TemplateResponse(request, "home.html", {
        "deals": deals, "stats": deal_stats_today(db), "stock_value": stock_value_at_cost(db), "cash": cash_available(db),
        "month_profit": realised_profit(db, start, end), "avg_days": avg_days_to_sell(db), "overdue": overdue, "tasks": tasks,
        "attention": attention, "today_start": today_start,
    })


@router.get("/health", response_class=HTMLResponse)
def health(request: Request, db: Session = Depends(get_db)):
    sources = db.scalars(select(Source).order_by(Source.kind, Source.name)).all()
    alerts = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(20)).all()
    from app.jobs.scheduler import job_summary
    return templates.TemplateResponse(request, "health.html", {"sources": sources, "alerts": alerts, "jobs": job_summary()})


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    sources = db.scalars(select(Source)).all()
    return {"status": "ok", "time": datetime.utcnow().isoformat(),
            "sources": {s.slug: {"enabled": s.enabled, "status": s.status, "message": s.status_message, "last_run": s.last_run_at.isoformat() if s.last_run_at else None} for s in sources}}


@router.post("/sources/{slug}/resume")
def resume_source(slug: str, db: Session = Depends(get_db)):
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src:
        src.status, src.status_message = "ok", ""
    return RedirectResponse("/health", status_code=303)


@router.post("/sources/{slug}/run")
def run_source_now(slug: str, db: Session = Depends(get_db)):
    from app.jobs.scheduler import run_source_job
    run_source_job(slug)
    return RedirectResponse("/health", status_code=303)


@router.post("/tasks/{task_id}/done")
def task_done(task_id: int, request: Request, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if t:
        t.done, t.done_at = True, datetime.utcnow()
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)
