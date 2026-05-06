from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate_invoice_pdf(*, order) -> bytes:
    """
    Minimal PDF invoice generator (ReportLab).

    For production:
    - use proper templates, branding, pagination
    - include tax/VAT, shipping, billing/shipping addresses, terms
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 48
    c.setFont("Helvetica-Bold", 16)
    c.drawString(48, y, "INVOICE")

    y -= 28
    c.setFont("Helvetica", 10)
    c.drawString(48, y, f"Invoice for Order: {order.public_id}")
    y -= 14
    c.drawString(48, y, f"Customer: {order.customer.username}")
    y -= 14
    c.drawString(48, y, f"Status: {order.status} | Payment: {order.payment_status}")
    y -= 14
    c.drawString(48, y, f"Created: {order.created_at}")

    y -= 26
    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, y, "Item")
    c.drawString(320, y, "Qty")
    c.drawString(370, y, "Unit")
    c.drawString(460, y, "Total")
    y -= 10
    c.line(48, y, width - 48, y)
    y -= 14

    c.setFont("Helvetica", 10)
    for item in order.items.filter(is_deleted=False).select_related("product"):
        if y < 80:
            c.showPage()
            y = height - 60
        c.drawString(48, y, item.product.name[:40])
        c.drawRightString(350, y, str(item.quantity))
        c.drawRightString(430, y, str(item.unit_price))
        c.drawRightString(width - 48, y, str(item.line_total))
        y -= 14

    y -= 8
    c.line(48, y, width - 48, y)
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 48, y, f"Grand Total: {order.total_amount}")

    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

