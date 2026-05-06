from django.contrib import admin

from .models import InventoryItem, InventoryTransaction, Purchase, PurchaseItem, VariantInventoryItem


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("product", "quantity_on_hand", "reorder_level", "updated_at")
    search_fields = ("product__name", "product__public_id")
    ordering = ("product__name",)


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "txn_type", "quantity_delta", "created_at", "order", "purchase")
    list_filter = ("txn_type", "created_at")
    search_fields = ("product__name", "product__public_id", "note")
    ordering = ("-created_at",)


@admin.register(VariantInventoryItem)
class VariantInventoryItemAdmin(admin.ModelAdmin):
    list_display = ("variant", "quantity_on_hand", "reorder_level", "updated_at")
    search_fields = ("variant__sku", "variant__product__name", "variant__product__public_id")
    ordering = ("variant__sku",)


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    autocomplete_fields = ("product",)
    readonly_fields = ("line_total", "created_at", "updated_at")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("public_id", "date", "supplier_name", "reference", "total_cost", "created_at")
    list_filter = ("date", "created_at")
    search_fields = ("public_id", "supplier_name", "reference", "note")
    ordering = ("-date", "-created_at")
    readonly_fields = ("public_id", "sequence_number", "sequence_year", "total_cost", "created_at", "updated_at")
    inlines = [PurchaseItemInline]
