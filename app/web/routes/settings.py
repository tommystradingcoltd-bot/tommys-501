"""Settings: fees, postage, tier rules, phase, base location, sources, notifications, niches."""
from __future__ import annotations

import json
from datetime import date

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import FeeConfig, Niche, PostageRate, SearchQuery, Source
from app.profit.distance import geocode
from app.settings_store import all_settings, set_setting
from app.web import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db), tab: str = "rules"):
    fees = db.scalars(select(FeeConfig).order_by(FeeConfig.group, FeeConfig.key)).all()
    postage = db.scalars(select(PostageRate).order_by(PostageRate.weight_class, PostageRate.price)).all()
    sources = db.scalars(select(Source).order_by(Source.kind, Source.name)).all()
    s = all_settings(db)
    env = get_settings()
    return templates.TemplateResponse(request, "settings.html", {
        "tab": tab, "fees": fees, "postage": postage, "sources": sources, "s": s, "env": env,
        "tier_json": json.dumps(s.get("tier_rules"), indent=1), "msg": request.query_params.get("msg", ""),
    })


@router.post("/settings/rules")
def save_rules(phase_mode: str = Form(...), min_net_profit: float = Form(...), capital_reserve: float = Form(...),
               large_deal_threshold: float = Form(...), large_deal_margin_relief: float = Form(...),
               low_confidence_min_margin: float = Form(...), steady_min_margin_override: float = Form(...),
               max_days_to_alert: int = Form(...), tier_rules: str = Form(...), listing_quality_uplift: float = Form(0.0),
               high_priority_score: float = Form(70), collection_max_miles: float = Form(40), monthly_buying_capacity: float = Form(4000),
               starting_capital: float = Form(5000), db: Session = Depends(get_db)):
    try:
        tiers = json.loads(tier_rules)
        assert isinstance(tiers, list) and all("max_days" in t and "min_margin" in t for t in tiers)
    except Exception:
        return RedirectResponse("/settings?tab=rules&msg=Tier+rules+must+be+a+JSON+list", status_code=303)
    for k, v in dict(phase_mode=phase_mode, min_net_profit=min_net_profit, capital_reserve=capital_reserve,
                     large_deal_threshold=large_deal_threshold, large_deal_margin_relief=large_deal_margin_relief / 100,
                     low_confidence_min_margin=low_confidence_min_margin / 100, steady_min_margin_override=steady_min_margin_override / 100,
                     max_days_to_alert=max_days_to_alert, tier_rules=tiers, listing_quality_uplift=listing_quality_uplift / 100,
                     high_priority_score=high_priority_score, collection_max_miles=collection_max_miles,
                     monthly_buying_capacity=monthly_buying_capacity, starting_capital=starting_capital).items():
        set_setting(db, k, v)
    return RedirectResponse("/settings?tab=rules&msg=Saved", status_code=303)


@router.post("/settings/location")
def save_location(postcode: str = Form(...), label: str = Form(""), db: Session = Depends(get_db)):
    pc = postcode.strip().upper()
    geo = geocode(pc, label)
    loc = {"postcode": pc, "label": label or pc, "lat": geo[0] if geo else None, "lon": geo[1] if geo else None}
    set_setting(db, "base_location", loc)
    msg = "Saved" if geo else "Saved,+but+postcode+area+not+recognised+(distance+will+be+unknown)"
    return RedirectResponse(f"/settings?tab=location&msg={msg}", status_code=303)


@router.post("/settings/fees/{fee_id}")
def save_fee(fee_id: int, value: float = Form(...), verified: str = Form(""), db: Session = Depends(get_db)):
    f = db.get(FeeConfig, fee_id)
    if f:
        f.value = value
        if verified:
            f.last_verified, f.verify_flag = date.today(), False
    return RedirectResponse("/settings?tab=fees", status_code=303)


@router.post("/settings/postage/{rate_id}")
def save_postage(rate_id: int, price: float = Form(...), verified: str = Form(""), default: str = Form(""), db: Session = Depends(get_db)):
    r = db.get(PostageRate, rate_id)
    if r:
        r.price = price
        if verified:
            r.last_verified, r.verify_flag = date.today(), False
        if default:
            for other in db.scalars(select(PostageRate).where(PostageRate.weight_class == r.weight_class)):
                other.default_for_class = other.id == r.id
    return RedirectResponse("/settings?tab=postage", status_code=303)


@router.post("/settings/postage/add")
def add_postage(carrier: str = Form(...), service: str = Form(...), weight_class: str = Form(...), max_weight_g: int = Form(...),
                price: float = Form(...), db: Session = Depends(get_db)):
    db.add(PostageRate(carrier=carrier, service=service, weight_class=weight_class, max_weight_g=max_weight_g, price=price,
                       tracked=True, last_verified=date.today(), verify_flag=False))
    return RedirectResponse("/settings?tab=postage", status_code=303)


@router.post("/settings/sources/{source_id}")
def save_source(source_id: int, enabled: str = Form(""), poll_interval_min: int = Form(15), max_page_loads_per_hour: int = Form(40),
                min_delay_s: int = Form(45), max_delay_s: int = Form(120), quiet_hours: str = Form("23-07"),
                buyer_fee_pct: float = Form(0.0), buyer_fee_fixed: float = Form(0.0), db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if src:
        src.enabled = bool(enabled)
        src.poll_interval_min, src.max_page_loads_per_hour = max(1, poll_interval_min), max(1, max_page_loads_per_hour)
        src.min_delay_s, src.max_delay_s, src.quiet_hours = min_delay_s, max(min_delay_s, max_delay_s), quiet_hours
        src.buyer_fee_pct, src.buyer_fee_fixed = buyer_fee_pct, buyer_fee_fixed
        src.config = {**(src.config or {}), "min_delay_s": min_delay_s, "max_delay_s": max_delay_s,
                      "max_page_loads_per_hour": max_page_loads_per_hour, "quiet_hours": quiet_hours}
        if src.enabled and src.status == "disabled":
            src.status = "ok"
        from app.jobs.scheduler import reschedule_sources
        reschedule_sources()
    return RedirectResponse("/settings?tab=sources", status_code=303)


@router.post("/settings/notifications")
def save_notifications(notify_quiet_hours: str = Form("22-07"), db: Session = Depends(get_db)):
    set_setting(db, "notify_quiet_hours", notify_quiet_hours)
    return RedirectResponse("/settings?tab=notifications&msg=Saved", status_code=303)


@router.post("/settings/notifications/test")
def test_notification(db: Session = Depends(get_db)):
    from app.notify.base import Notification
    from app.notify.service import get_notifier
    ok = get_notifier().send(Notification(title="DealFinder test", body="If you can read this, push notifications work.", priority="default"))
    return RedirectResponse(f"/settings?tab=notifications&msg={'Sent' if ok else 'Send+failed+-+check+NTFY_TOPIC'}", status_code=303)


# ---- niches ------------------------------------------------------------
@router.get("/niches", response_class=HTMLResponse)
def niches(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Niche).order_by(Niche.name)).all()
    return templates.TemplateResponse(request, "niches.html", {"niches": rows, "msg": request.query_params.get("msg", "")})


@router.get("/niches/{niche_id}", response_class=HTMLResponse)
def niche_detail(niche_id: int, request: Request, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if not n:
        return RedirectResponse("/niches", status_code=303)
    return templates.TemplateResponse(request, "niche_detail.html", {"niche": n, "yaml": yaml.safe_dump(n.config, sort_keys=False, allow_unicode=True),
                                                                     "queries": n.search_queries, "msg": request.query_params.get("msg", "")})


@router.post("/niches/new")
def niche_new(slug: str = Form(...), name: str = Form(...), search_terms: str = Form(""), db: Session = Depends(get_db)):
    slug = slug.strip().lower().replace(" ", "_")
    if db.scalar(select(Niche).where(Niche.slug == slug)):
        return RedirectResponse("/niches?msg=Slug+already+exists", status_code=303)
    terms = [t.strip() for t in search_terms.splitlines() if t.strip()]
    template = db.scalar(select(Niche).where(Niche.slug == "retro_games"))
    cfg = {"slug": slug, "name": name, "search_terms": terms, "platforms": {}, "normalisation_hints": "", "risk_keywords": {},
           "testing_checklist": {"game": [{"key": "works", "label": "Functions as intended"}]},
           "postage_classes": (template.config.get("postage_classes") if template else {}) or {"game_loose": "large_letter", "game_boxed": "small_parcel", "console": "medium_parcel", "bundle": "medium_parcel", "accessory": "small_parcel"},
           "photo_shot_list": {"game": ["Front", "Back", "Any damage close-up"]}}
    n = Niche(slug=slug, name=name, config=cfg, active=True)
    db.add(n)
    db.flush()
    for t in terms:
        db.add(SearchQuery(niche_id=n.id, query=t, filters={}))
    return RedirectResponse(f"/niches/{n.id}?msg=Created", status_code=303)


@router.post("/niches/{niche_id}/config")
def niche_config_save(niche_id: int, config_yaml: str = Form(...), active: str = Form(""), db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if not n:
        return RedirectResponse("/niches", status_code=303)
    try:
        cfg = yaml.safe_load(config_yaml) or {}
        assert isinstance(cfg, dict)
    except Exception as e:
        return RedirectResponse(f"/niches/{niche_id}?msg=Invalid+YAML:+{str(e)[:60]}", status_code=303)
    cfg["slug"], cfg["name"] = n.slug, cfg.get("name", n.name)
    n.config, n.name, n.active = cfg, cfg["name"], bool(active)
    existing = {q.query for q in n.search_queries}
    for t in cfg.get("search_terms", []):
        if t not in existing:
            db.add(SearchQuery(niche_id=n.id, query=t, filters=dict(cfg.get("default_filters", {}))))
    return RedirectResponse(f"/niches/{niche_id}?msg=Saved", status_code=303)


@router.post("/niches/{niche_id}/queries")
def niche_query_add(niche_id: int, query: str = Form(...), max_price: float = Form(0), db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n and query.strip():
        db.add(SearchQuery(niche_id=n.id, query=query.strip(), filters={"max_price": max_price} if max_price else {}))
    return RedirectResponse(f"/niches/{niche_id}", status_code=303)


@router.post("/niches/{niche_id}/queries/{query_id}/toggle")
def niche_query_toggle(niche_id: int, query_id: int, db: Session = Depends(get_db)):
    q = db.get(SearchQuery, query_id)
    if q:
        q.active = not q.active
    return RedirectResponse(f"/niches/{niche_id}", status_code=303)
