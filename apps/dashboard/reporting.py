from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Iterable

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass(frozen=True)
class ReportRange:
    label: str
    start: datetime
    end: datetime


def _start_of_day(d: date) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime(d.year, d.month, d.day, 0, 0, 0), timezone=tz)


def _end_of_day(d: date) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime(d.year, d.month, d.day, 23, 59, 59, 999999), timezone=tz)


def compute_report_range(*, period: str, start_date: date | None, end_date: date | None) -> ReportRange:
    now = timezone.localtime(timezone.now())
    today = now.date()

    period = (period or "").strip().lower() or "daily"
    if period == "weekly":
        start = _start_of_day(today - timedelta(days=6))
        end = _end_of_day(today)
        return ReportRange(label="Last 7 days", start=start, end=end)

    if period == "monthly":
        first = today.replace(day=1)
        start = _start_of_day(first)
        end = _end_of_day(today)
        return ReportRange(label=today.strftime("%B %Y"), start=start, end=end)

    if period == "custom":
        if not start_date and not end_date:
            start = _start_of_day(today)
            end = _end_of_day(today)
            return ReportRange(label="Custom (today)", start=start, end=end)
        start = _start_of_day(start_date or end_date or today)
        end = _end_of_day(end_date or start_date or today)
        if end < start:
            start, end = end, start
        label = f"{timezone.localtime(start).date().isoformat()} to {timezone.localtime(end).date().isoformat()}"
        return ReportRange(label=label, start=start, end=end)

    # daily (default)
    start = _start_of_day(today)
    end = _end_of_day(today)
    return ReportRange(label=today.isoformat(), start=start, end=end)


def generate_orders_report_pdf(*, title: str, subtitle: str, rows: Iterable[list[str]]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 8),
    ]

    data = [
        ["Date", "Order", "Customer", "Status", "Payment", "Total"],
        *list(rows),
    ]
    table = Table(data, repeatRows=1, hAlign="LEFT", colWidths=[30 * mm, 45 * mm, 55 * mm, 35 * mm, 35 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

