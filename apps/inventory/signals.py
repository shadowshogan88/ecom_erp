from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.products.models import Product, ProductVariant

from .models import InventoryItem, VariantInventoryItem


@receiver(post_save, sender=Product)
def ensure_inventory_item(sender, instance: Product, created: bool, **kwargs):
    if not created:
        return
    InventoryItem.objects.get_or_create(product=instance)


@receiver(post_save, sender=ProductVariant)
def ensure_variant_inventory_item(sender, instance: ProductVariant, created: bool, **kwargs):
    if not created:
        return
    VariantInventoryItem.objects.get_or_create(variant=instance)


def ensure_inventory_rows(sender, **kwargs):
    """
    Ensure InventoryItem / VariantInventoryItem exist for all existing products/variants.

    Helpful when new models are introduced into an existing database.
    """
    product_ids = list(Product.objects.values_list("id", flat=True))
    existing = set(InventoryItem.objects.filter(product_id__in=product_ids).values_list("product_id", flat=True))
    missing = [pid for pid in product_ids if pid not in existing]
    if missing:
        InventoryItem.objects.bulk_create([InventoryItem(product_id=pid) for pid in missing], ignore_conflicts=True)

    variant_ids = list(ProductVariant.objects.values_list("id", flat=True))
    existing_variants = set(
        VariantInventoryItem.objects.filter(variant_id__in=variant_ids).values_list("variant_id", flat=True)
    )
    missing_variants = [vid for vid in variant_ids if vid not in existing_variants]
    if missing_variants:
        VariantInventoryItem.objects.bulk_create(
            [VariantInventoryItem(variant_id=vid) for vid in missing_variants], ignore_conflicts=True
        )
