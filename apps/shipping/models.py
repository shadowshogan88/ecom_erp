from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import SoftDeleteModel, TimeStampedModel


class DeliveryZone(SoftDeleteModel, TimeStampedModel):
    """
    Simple zone model (country/region/postal prefixes as text).

    For production, you'd typically normalize these fields or integrate a
    dedicated shipping/rates service.
    """

    name = models.CharField(max_length=100, unique=True, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    countries = models.TextField(blank=True, help_text="Comma-separated country codes (e.g., BD,IN).")
    regions = models.TextField(blank=True, help_text="Comma-separated regions/cities.")
    postal_prefixes = models.TextField(blank=True, help_text="Comma-separated postal code prefixes.")

    fixed_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    per_item_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    free_shipping_min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def estimate_cost(self, *, order_total: Decimal, item_count: int) -> Decimal:
        if self.free_shipping_min_amount and order_total >= self.free_shipping_min_amount:
            return Decimal("0.00")
        item_count = max(int(item_count or 0), 0)
        return Decimal(self.fixed_cost or 0) + (Decimal(self.per_item_cost or 0) * Decimal(item_count))


class Courier(SoftDeleteModel, TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    tracking_url_template = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional template, e.g. https://courier.example/track/{tracking_number}",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"]),
        ]

    def __str__(self) -> str:
        return self.name

    def tracking_url(self, tracking_number: str) -> str:
        if not self.tracking_url_template:
            return ""
        return self.tracking_url_template.replace("{tracking_number}", tracking_number or "")


class Shipment(SoftDeleteModel, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="shipment")
    zone = models.ForeignKey(DeliveryZone, on_delete=models.PROTECT, related_name="shipments", null=True, blank=True)
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="shipments", null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    tracking_number = models.CharField(max_length=100, blank=True, db_index=True)

    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipped_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["tracking_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.order_id} - {self.status}"

    @property
    def courier_tracking_url(self) -> str:
        if not self.courier_id:
            return ""
        return self.courier.tracking_url(self.tracking_number)

    def set_status(self, *, status: str, note: str = ""):
        if status == self.status:
            return
        self.status = status

        now = timezone.now()
        if status == Shipment.Status.SHIPPED and not self.shipped_at:
            self.shipped_at = now
        if status == Shipment.Status.DELIVERED and not self.delivered_at:
            self.delivered_at = now

        if note:
            self.note = (self.note or "").strip() + ("\n" if self.note else "") + note

        self.save(update_fields=["status", "shipped_at", "delivered_at", "note", "updated_at"])
        ShipmentTrackingEvent.objects.create(shipment=self, status=status, note=note or "Status updated")


class ShipmentTrackingEvent(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="tracking_events")
    status = models.CharField(max_length=20, choices=Shipment.Status.choices, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["shipment", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.shipment_id} - {self.status}"
