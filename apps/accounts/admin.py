from django.contrib import admin

from .models import Expense, Income, LedgerEntry


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ("public_id", "date", "title", "amount", "order")
    list_filter = ("date", "created_at")
    search_fields = ("public_id", "title", "note")
    ordering = ("-date", "-created_at")
    readonly_fields = ("public_id", "sequence_number", "sequence_year", "sequence_month", "created_at", "updated_at")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("public_id", "date", "title", "category", "amount")
    list_filter = ("date", "category", "created_at")
    search_fields = ("public_id", "title", "category", "note")
    ordering = ("-date", "-created_at")
    readonly_fields = ("public_id", "sequence_number", "sequence_year", "sequence_month", "created_at", "updated_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_type", "date", "amount", "narration", "income", "expense")
    list_filter = ("entry_type", "date")
    search_fields = ("narration",)
    ordering = ("-date", "-created_at")
