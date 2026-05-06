from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Expense, Income, LedgerEntry


@receiver(post_save, sender=Income)
def ensure_income_ledger_entry(sender, instance: Income, created: bool, **kwargs):
    if not created:
        return
    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.INCOME,
        date=instance.date,
        amount=instance.amount,
        narration=instance.title,
        income=instance,
    )


@receiver(post_save, sender=Expense)
def ensure_expense_ledger_entry(sender, instance: Expense, created: bool, **kwargs):
    if not created:
        return
    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.EXPENSE,
        date=instance.date,
        amount=instance.amount,
        narration=instance.title,
        expense=instance,
    )

