from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils.id_generator import next_monthly_id


class Order(SoftDeleteModel, TimeStampedModel):
    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    sequence_month = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True
    )

    mobile_number = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["payment_status", "created_at"]),
            models.Index(fields=["sequence_year", "sequence_month", "sequence_number"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.public_id or f"Order #{self.pk}"

    @property
    def is_cancelled(self) -> bool:
        return self.status == Order.Status.CANCELLED

    def recalculate_totals(self, *, save: bool = True):
        total = (
            self.items.filter(is_deleted=False).aggregate(total=models.Sum("line_total")).get("total")
            or Decimal("0.00")
        )
        self.total_amount = total
        if save:
            self.save(update_fields=["total_amount", "updated_at"])
        return total

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            monthly = next_monthly_id(Order, prefix="ORD")
            self.public_id = monthly.public_id
            self.sequence_number = monthly.sequence_number
            self.sequence_year = monthly.sequence_year
            self.sequence_month = monthly.sequence_month
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.public_id = ""
                self.sequence_number = 0
                self.sequence_year = 0
                self.sequence_month = 0
                continue
        raise RuntimeError("Failed to generate a unique order public_id after multiple attempts.")


class OrderItem(SoftDeleteModel, TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = (("order", "product"),)
        indexes = [
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["order", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.order_id} - {self.product_id} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_price or Decimal("0.00")) * Decimal(self.quantity or 0)
        return super().save(*args, **kwargs)


class OrderTracking(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tracking")
    status = models.CharField(max_length=20, choices=Order.Status.choices, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["order", "timestamp"]),
            models.Index(fields=["status", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.order_id} - {self.status} @ {self.timestamp}"
