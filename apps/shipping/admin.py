from django.contrib import admin

from .models import Courier, DeliveryZone, Shipment, ShipmentTrackingEvent


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "fixed_cost", "per_item_cost", "free_shipping_min_amount")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "tracking_number", "zone", "courier", "shipped_at", "delivered_at", "created_at")
    list_filter = ("status", "zone", "courier", "shipped_at", "delivered_at", "created_at")
    search_fields = ("order__public_id", "tracking_number")
    ordering = ("-created_at",)


@admin.register(ShipmentTrackingEvent)
class ShipmentTrackingEventAdmin(admin.ModelAdmin):
    list_display = ("shipment", "status", "timestamp", "note")
    list_filter = ("status", "timestamp")
    search_fields = ("shipment__order__public_id", "note")
    ordering = ("-timestamp",)
