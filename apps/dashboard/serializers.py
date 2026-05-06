from __future__ import annotations

from rest_framework import serializers

from apps.orders.models import Order

from .models import Notification


class RecentOrderSerializer(serializers.ModelSerializer):
    customer_username = serializers.CharField(source="customer.username", read_only=True)

    class Meta:
        model = Order
        fields = ["public_id", "customer_username", "status", "payment_status", "total_amount", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "notification_type", "title", "message", "url", "is_read", "created_at"]

