from django.contrib import admin

from .models import Order, OrderItem, OrderTracking


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("product",)
    readonly_fields = ("line_total", "created_at", "updated_at")


class OrderTrackingInline(admin.TabularInline):
    model = OrderTracking
    extra = 0
    readonly_fields = ("status", "timestamp", "note")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "customer",
        "status",
        "payment_status",
        "subtotal_amount",
        "discount_amount",
        "shipping_amount",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "payment_status", "created_at", "updated_at")
    search_fields = ("public_id", "customer__username", "customer__email", "customer__public_id")
    ordering = ("-created_at",)
    autocomplete_fields = ("customer",)
    readonly_fields = (
        "public_id",
        "sequence_number",
        "sequence_year",
        "sequence_month",
        "subtotal_amount",
        "discount_amount",
        "shipping_amount",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline, OrderTrackingInline]
