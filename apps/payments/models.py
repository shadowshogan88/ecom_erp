from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils.id_generator import next_monthly_id


class Payment(SoftDeleteModel, TimeStampedModel):
    class Method(models.TextChoices):
        BKASH = "bkash", "Bkash"
        NAGAD = "nagad", "Nagad"
        CARD = "card", "Card"
        COD = "cod", "Cash on Delivery"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    sequence_month = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments", db_index=True
    )

    method = models.CharField(max_length=20, choices=Method.choices, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    transaction_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_reference = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    raw_payload = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_payments",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "created_at"]),
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["method", "status", "created_at"]),
            models.Index(fields=["sequence_year", "sequence_month", "sequence_number"]),
        ]

    def __str__(self) -> str:
        return self.public_id or f"Payment #{self.pk}"

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        if not self.customer_id and self.order_id:
            self.customer_id = self.order.customer_id

        for _ in range(5):
            monthly = next_monthly_id(Payment, prefix="PAY")
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
        raise RuntimeError("Failed to generate a unique payment public_id after multiple attempts.")


class Refund(SoftDeleteModel, TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reason = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_refunds",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payment", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Refund {self.amount} ({self.status})"


class PaymentEvent(TimeStampedModel):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="events", null=True, blank=True)
    event_type = models.CharField(max_length=50, db_index=True)
    message = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.created_at}"


def mark_payment_paid(*, payment: Payment, note: str = "") -> Payment:
    payment.status = Payment.Status.PAID
    if not payment.paid_at:
        payment.paid_at = timezone.now()
    if note:
        payment.note = (payment.note or "").strip() + ("\n" if payment.note else "") + note
    payment.save(update_fields=["status", "paid_at", "note", "updated_at"])
    return payment
