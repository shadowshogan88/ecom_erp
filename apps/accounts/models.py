from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils.id_generator import next_monthly_id


class Income(SoftDeleteModel, TimeStampedModel):
    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    sequence_month = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    title = models.CharField(max_length=255, db_index=True)
    note = models.TextField(blank=True)

    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="incomes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_incomes"
    )

    class Meta:
        indexes = [
            models.Index(fields=["sequence_year", "sequence_month", "sequence_number"]),
            models.Index(fields=["date", "amount"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.public_id or f"Income #{self.pk}"

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            monthly = next_monthly_id(Income, prefix="INC")
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
        raise RuntimeError("Failed to generate a unique income public_id after multiple attempts.")


class Expense(SoftDeleteModel, TimeStampedModel):
    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    sequence_month = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    title = models.CharField(max_length=255, db_index=True)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    note = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_expenses"
    )

    class Meta:
        indexes = [
            models.Index(fields=["sequence_year", "sequence_month", "sequence_number"]),
            models.Index(fields=["date", "amount"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.public_id or f"Expense #{self.pk}"

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            monthly = next_monthly_id(Expense, prefix="EXP")
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
        raise RuntimeError("Failed to generate a unique expense public_id after multiple attempts.")


class LedgerEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    entry_type = models.CharField(max_length=20, choices=EntryType.choices, db_index=True)
    date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    narration = models.CharField(max_length=255, blank=True)

    income = models.OneToOneField(Income, on_delete=models.CASCADE, null=True, blank=True, related_name="ledger_entry")
    expense = models.OneToOneField(Expense, on_delete=models.CASCADE, null=True, blank=True, related_name="ledger_entry")

    class Meta:
        indexes = [
            models.Index(fields=["entry_type", "date"]),
            models.Index(fields=["date", "amount"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount} on {self.date}"
