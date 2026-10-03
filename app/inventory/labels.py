"""Printable SKU label PDF (62x29mm-ish, fits a Brother/Dymo label or an A4 sheet of them)."""
from __future__ import annotations

import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models import InventoryItem

LABEL_W, LABEL_H = 62 * mm, 29 * mm


def label_pdf(items: list[InventoryItem]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(LABEL_W, LABEL_H))
    for item in items:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(3 * mm, LABEL_H - 6 * mm, item.sku)
        c.setFont("Helvetica", 7)
        title = f"{item.platform} {item.title}"[:48]
        c.drawString(3 * mm, LABEL_H - 10 * mm, title)
        c.drawString(3 * mm, LABEL_H - 13.5 * mm, f"{item.completeness or ''} {item.region or ''} cost £{item.cost_basis:.2f} {item.purchase_date:%d/%m/%y}".strip())
        bc = code128.Code128(item.sku, barHeight=9 * mm, barWidth=0.33)
        bc.drawOn(c, 3 * mm, 2 * mm)
        c.showPage()
    c.save()
    return buf.getvalue()
