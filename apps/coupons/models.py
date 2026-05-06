from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import SoftDeleteModel, TimeStampedModel


class PromoCode(SoftDeleteModel, TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FIXED = "fixed", "Fixed amount"
        BXGY = "bxgy", "Buy X Get Y"
        FREE_SHIPPING = "free_shipping", "Free shipping"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    discount_type = models.CharField(max_length=30, choices=DiscountType.choices, db_index=True)
    percent_off = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    amount_off = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    bxgy_buy_qty = models.PositiveIntegerField(default=0)
    bxgy_get_qty = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True, db_index=True)
    auto_apply = models.BooleanField(default=False, db_index=True)

    starts_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)

    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    one_time_per_user = models.BooleanField(default=False, help_text="If enabled, each user can redeem once.")
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Optional global usage limit.")
    times_redeemed = models.PositiveIntegerField(default=0, editable=False)

    # Targeting rules
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="allowed_promo_codes"
    )
    applicable_products = models.ManyToManyField(
        "products.Product", blank=True, related_name="promo_codes"
    )
    applicable_categories = models.ManyToManyField(
        "products.Category", blank=True, related_name="promo_codes"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_deleted", "is_active", "auto_apply"]),
            models.Index(fields=["discount_type", "is_active"]),
            models.Index(fields=["ends_at"]),
        ]

    def __str__(self) -> str:
        return self.code

    def is_currently_active(self) -> bool:
        if self.is_deleted or not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class PromoRedemption(TimeStampedModel):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="promo_redemptions")
    order = models.OneToOneField("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="promo_redemption")

    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    applied_via_auto = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["promo_code", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.promo_code_id} {self.user_id} {self.created_at}"

