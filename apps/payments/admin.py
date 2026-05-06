from django.contrib import admin

from .models import Payment, PaymentEvent, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("public_id", "order", "customer", "method", "status", "amount", "paid_at", "created_at")
    list_filter = ("method", "status", "paid_at", "created_at")
    search_fields = ("public_id", "order__public_id", "customer__username", "transaction_id", "provider_reference")
    ordering = ("-created_at",)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "status", "amount", "processed_at", "created_at")
    list_filter = ("status", "processed_at", "created_at")
    search_fields = ("payment__public_id", "reason")
    ordering = ("-created_at",)


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "payment", "message", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("event_type", "message", "payment__public_id")
    ordering = ("-created_at",)

# Register your models here.
