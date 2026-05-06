from __future__ import annotations

from django.contrib import admin

from .models import PromoCode, PromoRedemption


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "is_active", "auto_apply", "ends_at", "times_redeemed", "created_at")
    list_filter = ("discount_type", "is_active", "auto_apply", "ends_at")
    search_fields = ("code", "name", "description")


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = ("promo_code", "user", "order", "discount_amount", "created_at")
    list_filter = ("created_at", "applied_via_auto")
    search_fields = ("promo_code__code", "user__username", "order__public_id")

