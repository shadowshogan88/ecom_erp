from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils.id_generator import next_yearly_id


class InventoryItem(TimeStampedModel):
    product = models.OneToOneField("products.Product", on_delete=models.CASCADE, related_name="inventory_item")
    quantity_on_hand = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    last_counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["quantity_on_hand"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} ({self.quantity_on_hand})"


class VariantInventoryItem(TimeStampedModel):
    variant = models.OneToOneField("products.ProductVariant", on_delete=models.CASCADE, related_name="inventory_item")
    quantity_on_hand = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    last_counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["quantity_on_hand"]),
        ]

    def __str__(self) -> str:
        return f"{self.variant_id} ({self.quantity_on_hand})"


class InventoryTransaction(TimeStampedModel):
    class TxnType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="inventory_transactions")
    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    quantity_delta = models.IntegerField()
    note = models.TextField(blank=True)

    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_transactions")
    purchase = models.ForeignKey("inventory.Purchase", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_transactions")

    class Meta:
        indexes = [
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["txn_type", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.txn_type} {self.quantity_delta} for {self.product_id}"


class Purchase(SoftDeleteModel, TimeStampedModel):
    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    date = models.DateField(default=timezone.localdate, db_index=True)
    supplier_name = models.CharField(max_length=255, blank=True, db_index=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    note = models.TextField(blank=True)

    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [
            models.Index(fields=["sequence_year", "sequence_number"]),
            models.Index(fields=["date"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.public_id or f"Purchase #{self.pk}"

    def recalculate_totals(self, *, save: bool = True):
        total = self.items.filter(is_deleted=False).aggregate(total=models.Sum("line_total")).get("total") or Decimal("0.00")
        self.total_cost = total
        if save:
            self.save(update_fields=["total_cost", "updated_at"])
        return total

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            yearly = next_yearly_id(Purchase, prefix="PUR")
            self.public_id = yearly.public_id
            self.sequence_number = yearly.sequence_number
            self.sequence_year = yearly.sequence_year
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.public_id = ""
                self.sequence_number = 0
                self.sequence_year = 0
                continue
        raise RuntimeError("Failed to generate a unique purchase public_id after multiple attempts.")


class PurchaseItem(SoftDeleteModel, TimeStampedModel):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="purchase_items")

    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = (("purchase", "product"),)
        indexes = [
            models.Index(fields=["purchase", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_id} - {self.product_id} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_cost or Decimal("0.00")) * Decimal(self.quantity or 0)
        return super().save(*args, **kwargs)
