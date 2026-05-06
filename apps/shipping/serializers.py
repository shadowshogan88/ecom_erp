from __future__ import annotations

from rest_framework import serializers

from apps.orders.models import Order

from .models import Courier, DeliveryZone, Shipment, ShipmentTrackingEvent


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "code",
            "is_active",
            "countries",
            "regions",
            "postal_prefixes",
            "fixed_cost",
            "per_item_cost",
            "free_shipping_min_amount",
        ]


class CourierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courier
        fields = ["id", "name", "is_active", "tracking_url_template"]


class ShipmentTrackingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentTrackingEvent
        fields = ["status", "timestamp", "note"]


class ShipmentSerializer(serializers.ModelSerializer):
    order_public_id = serializers.CharField(source="order.public_id", read_only=True)
    courier_tracking_url = serializers.CharField(read_only=True)
    tracking_events = ShipmentTrackingEventSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "order_public_id",
            "status",
            "tracking_number",
            "shipping_cost",
            "zone",
            "courier",
            "courier_tracking_url",
            "shipped_at",
            "delivered_at",
            "note",
            "tracking_events",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "courier_tracking_url", "tracking_events"]


class ShipmentCreateSerializer(serializers.Serializer):
    order_public_id = serializers.CharField()
    zone_id = serializers.IntegerField(required=False, allow_null=True)
    courier_id = serializers.IntegerField(required=False, allow_null=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    shipping_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_order_public_id(self, value: str):
        order = Order.objects.filter(public_id=value, is_deleted=False).first()
        if not order:
            raise serializers.ValidationError("Order not found.")
        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError("Cannot create shipment for cancelled order.")
        return value

    def create(self, validated_data):
        order = Order.objects.get(public_id=validated_data["order_public_id"])
        shipment, _ = Shipment.objects.get_or_create(order=order)
        if "zone_id" in validated_data:
            shipment.zone_id = validated_data.get("zone_id")
        if "courier_id" in validated_data:
            shipment.courier_id = validated_data.get("courier_id")
        if "tracking_number" in validated_data:
            shipment.tracking_number = validated_data.get("tracking_number", "")
        if "shipping_cost" in validated_data:
            shipment.shipping_cost = validated_data.get("shipping_cost") or shipment.shipping_cost
        if "note" in validated_data:
            shipment.note = validated_data.get("note", "")
        shipment.save()
        return shipment


class ShipmentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Shipment.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True)

