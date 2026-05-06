from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Expense, Income
from apps.inventory.models import InventoryItem, VariantInventoryItem
from apps.orders.models import Order
from apps.users.permissions import IsStaffUser


def _parse_range(request, *, default_days: int = 30):
    start_raw = request.GET.get("start")
    end_raw = request.GET.get("end")
    end = parse_date(end_raw) if end_raw else timezone.localdate()
    start = parse_date(start_raw) if start_raw else (end - timedelta(days=default_days))
    if not start:
        start = end - timedelta(days=default_days)
    if not end:
        end = timezone.localdate()
    if start > end:
        start, end = end, start
    return start, end


class SalesReportAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        start, end = _parse_range(request)
        qs = (
            Order.objects.filter(
                is_deleted=False,
                payment_status=Order.PaymentStatus.PAID,
                created_at__date__gte=start,
                created_at__date__lte=end,
            )
            .exclude(status=Order.Status.CANCELLED)
            .order_by()
        )
        totals = qs.aggregate(revenue=Sum("total_amount"), orders=Count("id"))
        series = list(
            qs.annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(revenue=Sum("total_amount"), orders=Count("id"))
            .order_by("day")
        )
        for r in series:
            r["day"] = r["day"].date().isoformat()
        return Response({"start": str(start), "end": str(end), "totals": totals, "series": series})


class InventoryLowStockReportAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        products = (
            InventoryItem.objects.filter(reorder_level__gt=0, quantity_on_hand__lte=F("reorder_level"))
            .select_related("product")
            .order_by("quantity_on_hand")
        )
        variants = (
            VariantInventoryItem.objects.filter(reorder_level__gt=0, quantity_on_hand__lte=F("reorder_level"))
            .select_related("variant__product")
            .order_by("quantity_on_hand")
        )

        return Response(
            {
                "products": [
                    {
                        "product_public_id": i.product.public_id,
                        "product_name": i.product.name,
                        "qty": i.quantity_on_hand,
                        "reorder_level": i.reorder_level,
                    }
                    for i in products
                ],
                "variants": [
                    {
                        "sku": i.variant.sku,
                        "product_public_id": i.variant.product.public_id,
                        "product_name": i.variant.product.name,
                        "qty": i.quantity_on_hand,
                        "reorder_level": i.reorder_level,
                    }
                    for i in variants
                ],
            }
        )


class TopCustomersReportAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        User = get_user_model()
        rows = (
            User.objects.filter(is_active=True, role="customer")
            .annotate(
                total_spend=Sum(
                    "orders__total_amount",
                    filter=models.Q(
                        orders__is_deleted=False,
                        orders__payment_status=Order.PaymentStatus.PAID,
                    )
                    & ~models.Q(orders__status=Order.Status.CANCELLED),
                ),
                orders_count=Count(
                    "orders",
                    filter=models.Q(orders__is_deleted=False)
                    & ~models.Q(orders__status=Order.Status.CANCELLED),
                ),
            )
            .order_by(models.F("total_spend").desc(nulls_last=True), "-orders_count")[:20]
        )
        return Response(
            [
                {
                    "public_id": u.public_id,
                    "username": u.username,
                    "total_spend": u.total_spend or 0,
                    "orders_count": u.orders_count or 0,
                }
                for u in rows
            ]
        )


class ProfitLossReportAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        start, end = _parse_range(request)
        income = (
            Income.objects.filter(is_deleted=False, date__gte=start, date__lte=end)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        expense = (
            Expense.objects.filter(is_deleted=False, date__gte=start, date__lte=end)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        return Response({"start": str(start), "end": str(end), "income": income, "expense": expense, "profit": income - expense})

