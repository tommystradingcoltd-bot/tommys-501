"""Per-niche testing checklists stored against inventory items."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import InventoryItem, Niche, TestResult


def checklist_for(niche: Niche, category: str) -> list[dict]:
    cl = (niche.config or {}).get("testing_checklist", {})
    items = cl.get(category) or cl.get("game") or []
    if category == "bundle":
        items = (cl.get("console") or []) + (cl.get("game") or [])
        seen, out = set(), []
        for i in items:
            if i["key"] not in seen:
                seen.add(i["key"])
                out.append(i)
        items = out
    return [{"key": i["key"], "label": i["label"], "result": "", "notes": ""} for i in items]


def record_test(db: Session, item: InventoryItem, results: dict[str, str], notes: dict[str, str] | None = None,
                grade: str = "", summary: str = "") -> TestResult:
    """results: {key: 'pass'|'fail'|'na'}. Fails anywhere -> not passed."""
    niche = db.get(Niche, item.niche_id)
    checklist = checklist_for(niche, item.category)
    notes = notes or {}
    for row in checklist:
        row["result"] = results.get(row["key"], "")
        row["notes"] = notes.get(row["key"], "")
    passed = all(r["result"] in ("pass", "na") for r in checklist) and any(r["result"] == "pass" for r in checklist)
    tr = TestResult(inventory_item_id=item.id, checklist=checklist, passed=passed, grade=grade, notes=summary)
    db.add(tr)
    if item.status == "testing":
        item.status = "ready_to_photograph"
    db.flush()
    return tr
