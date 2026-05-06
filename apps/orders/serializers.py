from __future__ import annotations

from collections import defaultdict
from rest_framework import serializers

from .models import Order, OrderItem, OrderTracking
from .services import DuplicateOrderError, create_order_from_products


class OrderTrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderTracking
        fields = ["status", "timestamp", "note"]
        read_only_fields = fields


class OrderItemSerializer(serializers.ModelSerializer):
    product_public_id = serializers.CharField(source="product.public_id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "product_public_id",
            "product_name",
            "quantity",
            "unit_price",
            "line_total",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    tracking = OrderTrackingSerializer(many=True, read_only=True)
    customer_public_id = serializers.CharField(source="customer.public_id", read_only=True)

    class Meta:
        model = Order
        fields = [
            "public_id",
            "customer_public_id",
            "status",
            "payment_status",
            "mobile_number",
            "note",
            "total_amount",
            "created_at",
            "updated_at",
            "items",
            "tracking",
        ]
        read_only_fields = fields


class OrderCreateItemInputSerializer(serializers.Serializer):
    product_public_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderCreateItemInputSerializer(many=True)
    mobile_number = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("At least one item is required.")
        return items

    def create(self, validated_data):
        request = self.context["request"]
        customer = request.user

        requested_items = validated_data["items"]
        mobile_number = validated_data.get("mobile_number") or ""
        note = validated_data.get("note", "")

        quantities_by_product_public_id: dict[str, int] = defaultdict(int)
        for item in requested_items:
            quantities_by_product_public_id[item["product_public_id"]] += int(item["quantity"])

        try:
            order = create_order_from_products(
                customer=customer,
                quantities_by_product_public_id=dict(quantities_by_product_public_id),
                mobile_number=mobile_number,
                note=note,
            )
        except DuplicateOrderError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        except ValueError as exc:
            raise serializers.ValidationError({"items": str(exc)})
        return order


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
