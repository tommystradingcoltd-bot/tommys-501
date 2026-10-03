"""Weekly growth insights: gather my own data -> Claude (or rule-based mock) -> Markdown page + clone-readiness."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.pnl import accuracy, avg_days_to_sell, monthly_margins, pnl_by
from app.identification.llm import get_llm
from app.models import Deal, Insight, InventoryItem, Niche
from app.settings_store import get_setting


def gather_data(db: Session) -> dict:
    overdue = [i for i in db.scalars(select(InventoryItem).where(InventoryItem.status == "listed")) if i.is_overdue]
    since = datetime.utcnow() - timedelta(days=7)
    deals = db.scalars(select(Deal).where(Deal.created_at >= since)).all()
    by_source: dict[str, dict] = {}
    for d in deals:
        s = d.raw_listing.source.slug
        g = by_source.setdefault(s, {"deals": 0, "alerted": 0, "bought": 0, "avg_margin_alerted": 0.0})
        g["deals"] += 1
        if d.should_alert:
            g["alerted"] += 1
            g["avg_margin_alerted"] += d.net_margin
        if d.status == "bought":
            g["bought"] += 1
    for g in by_source.values():
        g["avg_margin_alerted"] = round(g["avg_margin_alerted"] / g["alerted"], 3) if g["alerted"] else 0.0
    return {
        "generated": date.today().isoformat(),
        "by_platform": _by_item_platform(db),
        "by_source": pnl_by(db, "source", 3),
        "by_sell_platform": pnl_by(db, "platform", 3),
        "monthly": monthly_margins(db, 4),
        "accuracy": accuracy(db, 6),
        "avg_days_to_sell_90d": avg_days_to_sell(db, 90),
        "overdue_stock": [{"sku": i.sku, "title": i.title, "days_listed": (datetime.utcnow() - (i.listed_at or datetime.utcnow())).days,
                           "expected_days": i.expected_days_to_sell, "cost": i.cost_basis} for i in overdue[:15]],
        "deal_flow_7d": by_source,
        "stock_count": len(db.scalars(select(InventoryItem.id).where(InventoryItem.status.notin_(["sold", "shipped"]))).all()),
    }


def _by_item_platform(db: Session) -> list[dict]:
    from collections import defaultdict
    from app.models import Sale
    since = datetime.utcnow() - timedelta(days=90)
    rows = db.execute(select(Sale, InventoryItem).join(InventoryItem, Sale.inventory_item_id == InventoryItem.id).where(Sale.sold_at >= since)).all()
    g: dict[str, dict] = defaultdict(lambda: {"count": 0, "revenue": 0.0, "profit": 0.0, "days": 0})
    for s, i in rows:
        k = f"{i.platform} / {i.category}"
        g[k]["count"] += 1
        g[k]["revenue"] += s.sale_price
        g[k]["profit"] += s.net_profit
        g[k]["days"] += s.days_to_sell
    return sorted([{"key": k, "count": v["count"], "revenue": round(v["revenue"], 2), "profit": round(v["profit"], 2),
                    "margin": round(v["profit"] / v["revenue"], 3) if v["revenue"] else 0, "avg_days": round(v["days"] / v["count"], 1)}
                   for k, v in g.items()], key=lambda r: -r["profit"])


def clone_ready(monthly: list[dict], rule: dict) -> tuple[bool, str]:
    need = int(rule.get("months", 3))
    recent = [m for m in monthly if m["sales"] > 0][-need:]
    if len(recent) < need:
        return False, f"need {need} months of sales data ({len(recent)} so far)"
    ok = all(m["margin"] >= rule["min_margin"] and (m["avg_days"] or 999) < rule["max_avg_days"] for m in recent)
    if ok:
        return True, f"{need} consecutive months at >= {rule['min_margin']:.0%} margin and < {rule['max_avg_days']} days to sell - ready to clone"
    bad = [m["month"] for m in recent if not (m["margin"] >= rule["min_margin"] and (m["avg_days"] or 999) < rule["max_avg_days"])]
    return False, f"not yet: months missing the bar: {', '.join(bad)}"


def rule_based_insights(data: dict) -> str:
    lines = ["# Weekly insights (rule-based; connect Claude for narrative analysis)", ""]
    bp = data.get("by_platform") or []
    lines.append("## What's selling fastest")
    fast = sorted(bp, key=lambda r: r["avg_days"])[:5]
    lines += [f"- {r['key']}: {r['avg_days']} days avg, {r['count']} sold" for r in fast] or ["- No sales yet."]
    lines.append("\n## Best margins by platform / category")
    lines += [f"- {r['key']}: {r['margin']:.0%} margin, £{r['profit']:.0f} profit on {r['count']} sales" for r in sorted(bp, key=lambda r: -r['margin'])[:5]] or ["- No sales yet."]
    lines.append("\n## Which sources give the best deals")
    bs = data.get("by_source") or []
    lines += [f"- {r['key']}: realised £{r['profit']:.0f} vs predicted £{r['predicted_profit']:.0f} ({r['count']} sales)" for r in sorted(bs, key=lambda r: -r['profit'])] or ["- No sales yet."]
    for s, g in (data.get("deal_flow_7d") or {}).items():
        lines.append(f"- {s}: {g['deals']} listings this week, {g['alerted']} alerted, {g['bought']} bought")
    lines.append("\n## Slow stock to mark down")
    lines += [f"- {o['sku']} {o['title'][:40]}: listed {o['days_listed']}d vs {o['expected_days']}d expected (cost £{o['cost']:.0f})" for o in data.get("overdue_stock", [])] or ["- Nothing overdue."]
    lines.append("\n## Buy more / buy less")
    if bp:
        lines.append(f"- Buy more: {fast[0]['key']} (fastest) and {sorted(bp, key=lambda r: -r['margin'])[0]['key']} (best margin)")
        slow = sorted(bp, key=lambda r: -r["avg_days"])[0]
        lines.append(f"- Buy less: {slow['key']} ({slow['avg_days']} days to sell)")
    else:
        lines.append("- Not enough sales data yet.")
    acc = data.get("accuracy") or {}
    lines.append("\n## Model accuracy")
    if acc.get("count"):
        lines.append(f"- {acc['count']} sales: mean profit error £{acc['mean_profit_error']:.2f} (abs £{acc['mean_abs_profit_error']:.2f}), "
                     f"days error {acc['mean_days_error']:+.1f}, {acc['within_20pct']:.0%} within 20% of predicted profit")
    else:
        lines.append("- No completed sales to compare yet.")
    lines.append("\n## Ready to clone?")
    lines.append(f"- {data.get('clone_reason', 'n/a')}")
    return "\n".join(lines)


def generate_weekly_insights(db: Session) -> Insight:
    data = gather_data(db)
    rule = get_setting(db, "clone_rule", {"months": 3, "min_margin": 0.3, "max_avg_days": 30})
    ready, reason = clone_ready(data["monthly"], rule)
    data["clone_ready"], data["clone_reason"] = ready, reason
    niche = db.scalar(select(Niche).where(Niche.active == True))  # noqa: E712
    md = get_llm().complete_text("insights", {"niche_name": niche.name if niche else "my niche",
                                              "starting_capital": f"{float(get_setting(db, 'starting_capital', 5000)):.0f}", "data": data}, max_tokens=3000)
    today = date.today()
    row = Insight(period_start=today - timedelta(days=7), period_end=today, content_md=md, data=data, ready_to_clone=ready)
    db.add(row)
    db.flush()
    return row
