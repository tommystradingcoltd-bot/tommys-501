"""Capital ledger, stock value, realised P&L and predicted-vs-actual accuracy."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CapitalLedger, Deal, InventoryItem, Sale
from app.settings_store import get_setting


# ---- capital ledger --------------------------------------------------------
def ledger_balance(db: Session) -> float:
    last = db.scalar(select(CapitalLedger).order_by(CapitalLedger.id.desc()).limit(1))
    return last.balance_after if last else 0.0


def ensure_opening_balance(db: Session) -> None:
    if db.scalar(select(CapitalLedger.id).limit(1)) is None:
        start = float(get_setting(db, "starting_capital", 5000.0))
        db.add(CapitalLedger(entry_type="deposit", amount=start, balance_after=start, note="Opening stock capital"))
        db.flush()


def post_ledger(db: Session, entry_type: str, amount: float, ref_type: str = "", ref_id: Optional[int] = None, note: str = "") -> CapitalLedger:
    bal = ledger_balance(db) + amount
    row = CapitalLedger(entry_type=entry_type, amount=round(amount, 2), balance_after=round(bal, 2), ref_type=ref_type, ref_id=ref_id, note=note[:200])
    db.add(row)
    db.flush()
    return row


def cash_available(db: Session) -> float:
    return round(ledger_balance(db), 2)


def stock_value_at_cost(db: Session) -> float:
    v = db.scalar(select(func.coalesce(func.sum(InventoryItem.cost_basis), 0.0)).where(
        InventoryItem.status.notin_(["sold", "shipped"])))
    return round(float(v or 0.0), 2)


# ---- realised P&L -----------------------------------------------------------
def month_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, 1)
    end = datetime(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return start, end


def realised_profit(db: Session, start: datetime, end: datetime) -> float:
    v = db.scalar(select(func.coalesce(func.sum(Sale.net_profit), 0.0)).where(Sale.sold_at >= start, Sale.sold_at < end))
    return round(float(v or 0), 2)


def avg_days_to_sell(db: Session, days: int = 90) -> Optional[float]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.scalars(select(Sale.days_to_sell).where(Sale.sold_at >= since)).all()
    return round(sum(rows) / len(rows), 1) if rows else None


def pnl_by(db: Session, key: str, months: int = 6) -> list[dict]:
    """key in: item | month | source | platform (selling platform)."""
    since = datetime.utcnow() - timedelta(days=30 * months)
    rows = db.execute(select(Sale, InventoryItem).join(InventoryItem, Sale.inventory_item_id == InventoryItem.id)
                      .where(Sale.sold_at >= since).order_by(Sale.sold_at.desc())).all()
    groups: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "cost": 0.0, "fees": 0.0, "profit": 0.0, "count": 0, "days": 0,
                                                   "predicted_profit": 0.0, "predicted_days": 0})
    for s, i in rows:
        if key == "item":
            k = f"{i.sku} {i.title[:40]}"
        elif key == "month":
            k = s.sold_at.strftime("%Y-%m")
        elif key == "source":
            k = i.source or "unknown"
        else:
            k = s.platform
        g = groups[k]
        g["revenue"] += s.sale_price
        g["cost"] += i.cost_basis
        g["fees"] += s.platform_fees + s.payment_fees + s.postage_cost + s.packaging_cost + s.other_costs
        g["profit"] += s.net_profit
        g["count"] += 1
        g["days"] += s.days_to_sell
        g["predicted_profit"] += i.expected_net_profit
        g["predicted_days"] += i.expected_days_to_sell
    out = []
    for k, g in groups.items():
        n = g["count"]
        out.append({"key": k, "count": n, "revenue": round(g["revenue"], 2), "cost": round(g["cost"], 2), "fees": round(g["fees"], 2),
                    "profit": round(g["profit"], 2), "margin": round(g["profit"] / g["revenue"], 3) if g["revenue"] else 0.0,
                    "avg_days": round(g["days"] / n, 1), "predicted_profit": round(g["predicted_profit"], 2),
                    "predicted_days": round(g["predicted_days"] / n, 1), "profit_error": round(g["profit"] - g["predicted_profit"], 2)})
    out.sort(key=lambda r: r["key"], reverse=(key == "month"))
    return out


def accuracy(db: Session, months: int = 6) -> dict:
    rows = pnl_by(db, "item", months)
    if not rows:
        return {"count": 0}
    n = len(rows)
    profit_err = [r["profit"] - r["predicted_profit"] for r in rows]
    days_err = [r["avg_days"] - r["predicted_days"] for r in rows]
    return {
        "count": n,
        "mean_profit_error": round(sum(profit_err) / n, 2),
        "mean_abs_profit_error": round(sum(abs(e) for e in profit_err) / n, 2),
        "mean_days_error": round(sum(days_err) / n, 1),
        "within_20pct": round(sum(1 for r in rows if r["predicted_profit"] and abs(r["profit_error"]) <= 0.2 * abs(r["predicted_profit"])) / n, 2),
    }


def monthly_margins(db: Session, months: int = 6) -> list[dict]:
    """Per-month realised margin and avg days (for the clone-readiness rule and projections)."""
    out = []
    today = date.today().replace(day=1)
    for i in range(months):
        m = today
        for _ in range(i):
            m = (m - timedelta(days=1)).replace(day=1)
        start, end = month_bounds(m)
        rows = db.scalars(select(Sale).where(Sale.sold_at >= start, Sale.sold_at < end)).all()
        rev = sum(s.sale_price for s in rows)
        profit = sum(s.net_profit for s in rows)
        out.append({"month": m.strftime("%Y-%m"), "sales": len(rows), "revenue": round(rev, 2), "profit": round(profit, 2),
                    "margin": round(profit / rev, 3) if rev else 0.0,
                    "avg_days": round(sum(s.days_to_sell for s in rows) / len(rows), 1) if rows else None})
    return list(reversed(out))


def learned_uplift(db: Session) -> Optional[float]:
    """Actual sale price vs predicted (median comp) across my sales: the listing-quality uplift."""
    rows = db.execute(select(Sale.sale_price, InventoryItem.expected_sale_price)
                      .join(InventoryItem, Sale.inventory_item_id == InventoryItem.id)
                      .where(InventoryItem.expected_sale_price > 0)).all()
    if len(rows) < 5:
        return None
    ratios = [s / e for s, e in rows if e]
    return round(sum(ratios) / len(ratios) - 1, 3)


def deal_stats_today(db: Session) -> dict:
    start = datetime.combine(date.today(), datetime.min.time())
    total = db.scalar(select(func.count(Deal.id)).where(Deal.created_at >= start)) or 0
    alerted = db.scalar(select(func.count(Deal.id)).where(Deal.created_at >= start, Deal.should_alert == True)) or 0  # noqa: E712
    return {"total": total, "alerted": alerted}
