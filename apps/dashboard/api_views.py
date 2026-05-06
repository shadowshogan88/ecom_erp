from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.inventory.models import InventoryItem
from apps.orders.models import Order
from apps.users.permissions import IsStaffUser

from .models import Notification
from .serializers import NotificationSerializer, RecentOrderSerializer


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        User = get_user_model()
        total_customers = User.objects.filter(is_active=True, role="customer").count()
        total_orders = Order.objects.filter(is_deleted=False).count()

        revenue = (
            Order.objects.filter(is_deleted=False, payment_status=Order.PaymentStatus.PAID)
            .exclude(status=Order.Status.CANCELLED)
            .aggregate(total=Sum("total_amount"))
            .get("total")
            or 0
        )

        low_stock = InventoryItem.objects.filter(reorder_level__gt=0).filter(
            quantity_on_hand__lte=models.F("reorder_level")
        ).count()

        unread_notifications = Notification.objects.filter(is_read=False).count()

        return Response(
            {
                "total_customers": total_customers,
                "total_orders": total_orders,
                "total_revenue": revenue,
                "low_stock_alerts": low_stock,
                "unread_notifications": unread_notifications,
            }
        )


class SalesAnalyticsAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        period = (request.GET.get("period") or "daily").lower()
        days = int(request.GET.get("days") or 30)
        days = max(1, min(days, 365))

        since = timezone.now() - timedelta(days=days)

        qs = (
            Order.objects.filter(is_deleted=False, created_at__gte=since, payment_status=Order.PaymentStatus.PAID)
            .exclude(status=Order.Status.CANCELLED)
            .order_by()
        )

        if period == "weekly":
            trunc = TruncWeek("created_at")
        elif period == "monthly":
            trunc = TruncMonth("created_at")
        else:
            trunc = TruncDay("created_at")

        rows = list(
            qs.annotate(bucket=trunc)
            .values("bucket")
            .annotate(revenue=Sum("total_amount"), orders=Count("id"))
            .order_by("bucket")
        )
        for r in rows:
            r["bucket"] = r["bucket"].date().isoformat() if hasattr(r["bucket"], "date") else str(r["bucket"])
        return Response({"period": period, "days": days, "series": rows})


class RecentOrdersAPIView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        orders = (
            Order.objects.filter(is_deleted=False)
            .select_related("customer")
            .order_by("-created_at")[:10]
        )
        return Response(RecentOrderSerializer(orders, many=True).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        user = self.request.user
        return Notification.objects.filter(models.Q(recipient__isnull=True) | models.Q(recipient=user)).order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        obj = self.get_object()
        if not obj.is_read:
            obj.is_read = True
            obj.save(update_fields=["is_read", "updated_at"])
        return Response(NotificationSerializer(obj).data, status=status.HTTP_200_OK)

