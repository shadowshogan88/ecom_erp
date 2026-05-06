from __future__ import annotations

"""
Variant generator service.

This module contains the backend logic for:
  - Tag-based attribute selection (AttributeValue IDs)
  - Cartesian-product variant generation
  - Deterministic "signature" for duplicate prevention
  - SKU auto-generation with uniqueness enforcement

Views (dashboard / AJAX) should call these helpers instead of re-implementing logic.
"""

from dataclasses import dataclass
from itertools import product as cartesian_product
from typing import Iterable

from django.db import transaction
from django.utils.text import slugify

from apps.products.models import Attribute, AttributeValue, Product, ProductVariant, VariantAttribute


def _normalize_piece(text: str) -> str:
    """
    Converts a human string to an SKU-safe segment.
    Examples:
      "Navy Blue" -> "NAVY-BLUE"
      "XL" -> "XL"
    """
    value = (text or "").strip()
    if not value:
        return ""
    return (slugify(value) or "").upper()


def product_code_for_sku(product: Product, *, max_len: int = 24) -> str:
    """
    Derive a product code for SKU generation.

    We prefer the product slug/name because the existing `public_id` contains `/` which is not ideal for SKUs.
    """
    base = (product.slug or product.name or "").strip()
    code = _normalize_piece(base) or "PRODUCT"
    return code[:max_len]


def signature_for_pairs(pairs: Iterable[tuple[int, int]]) -> str:
    """
    Stable per-product signature used to prevent duplicate variant combinations.

    `pairs` are (attribute_id, attribute_value_id). We sort by attribute_id to keep the signature deterministic.
    """
    items = sorted(pairs, key=lambda x: x[0])
    return ";".join([f"a{aid}=v{vid}" for aid, vid in items])


def sku_for_variant(
    *,
    product: Product,
    attribute_values: list[AttributeValue],
    existing_skus: set[str] | None = None,
) -> str:
    """
    SKU format (base requirement):
      PRODUCTCODE-COLOR-SIZE

    If attributes beyond Color/Size exist, we append them after Size in a stable order.
    If the generated SKU conflicts globally, we add a numeric suffix to keep it unique.
    """
    existing_skus = existing_skus or set()

    product_code = product_code_for_sku(product)

    # Order values: Color -> Size -> others (by attribute sort_order then name).
    by_attr: dict[int, AttributeValue] = {av.attribute_id: av for av in attribute_values}
    attrs = {av.attribute_id: av.attribute for av in attribute_values if hasattr(av, "attribute")}

    def _attr_key(attr: Attribute):
        name = (attr.name or "").strip().lower()
        if name == "color":
            return (0, attr.sort_order, attr.name)
        if name == "size":
            return (1, attr.sort_order, attr.name)
        return (2, attr.sort_order, attr.name)

    ordered_attrs = sorted(attrs.values(), key=_attr_key)
    pieces = [_normalize_piece(by_attr[a.id].value) for a in ordered_attrs]
    pieces = [p for p in pieces if p]

    base = "-".join([product_code] + pieces) if pieces else product_code
    sku = base[:64]

    # Use `all_objects` so we also avoid collisions with soft-deleted variants.
    # The DB unique constraint still applies to deleted rows.
    if sku not in existing_skus and not ProductVariant.all_objects.filter(sku=sku).exists():
        return sku

    # Fallback: add suffix until unique (still readable, remains deterministic-ish).
    for i in range(2, 5000):
        candidate = f"{base}-{i}"
        candidate = candidate[:64]
        if candidate in existing_skus:
            continue
        if not ProductVariant.all_objects.filter(sku=candidate).exists():
            return candidate

    raise RuntimeError("Unable to generate a unique SKU after many attempts.")


@dataclass(frozen=True)
class GeneratedVariantRow:
    """
    Result row returned by `generate_variants_for_product`.
    """

    variant: ProductVariant
    attribute_values: list[AttributeValue]
    created: bool


def generate_variants_for_product(
    *,
    product: Product,
    attribute_value_ids_by_attribute: dict[int, list[int]],
    set_first_default_if_none: bool = True,
) -> list[GeneratedVariantRow]:
    """
    Given selected AttributeValue IDs grouped by Attribute, generate all combinations.

    Duplicate prevention:
      - signature is unique per product (products_unique_variant_signature)
      - we also pre-check existing variants for signatures to avoid IntegrityError
    """
    # Clean/normalize incoming mapping.
    cleaned: dict[int, list[int]] = {}
    for attr_id, value_ids in (attribute_value_ids_by_attribute or {}).items():
        attr_id = int(attr_id)
        unique_ids: list[int] = []
        for vid in value_ids or []:
            vid = int(vid)
            if vid not in unique_ids:
                unique_ids.append(vid)
        if unique_ids:
            cleaned[attr_id] = unique_ids

    if not cleaned:
        return []

    # Load AttributeValues (with attributes) and validate membership.
    all_value_ids = [vid for vids in cleaned.values() for vid in vids]
    values = list(
        AttributeValue.objects.filter(is_deleted=False, is_active=True, id__in=all_value_ids).select_related("attribute")
    )
    value_by_id = {v.id: v for v in values}

    # Validate every submitted value exists and belongs to the provided attribute.
    for attr_id, vids in cleaned.items():
        for vid in vids:
            v = value_by_id.get(vid)
            if not v or v.attribute_id != attr_id:
                raise ValueError("Invalid attribute/value selection.")

    # Prepare stable attribute ordering for combination generation.
    attributes = list(
        Attribute.objects.filter(id__in=list(cleaned.keys()), is_deleted=False, is_active=True).order_by("sort_order", "name")
    )
    attr_ids_ordered = [a.id for a in attributes]

    value_lists: list[list[AttributeValue]] = [
        [value_by_id[vid] for vid in cleaned[attr_id]] for attr_id in attr_ids_ordered
    ]

    # Compute signatures for all requested combinations.
    combos: list[tuple[list[AttributeValue], str]] = []
    for combo in cartesian_product(*value_lists):
        pairs = [(av.attribute_id, av.id) for av in combo]
        combos.append((list(combo), signature_for_pairs(pairs)))

    signatures = [sig for _, sig in combos]
    existing_by_sig: dict[str, ProductVariant] = {
        v.signature: v
        for v in ProductVariant.all_objects.filter(product=product, signature__in=signatures)
        .select_related("product")
        .all()
        if v.signature
    }

    # Cache existing SKUs to reduce DB hits.
    existing_skus = set(
        ProductVariant.all_objects.filter(product=product).values_list("sku", flat=True)
    )

    results: list[GeneratedVariantRow] = []

    with transaction.atomic():
        for attr_values, sig in combos:
            existing_variant = existing_by_sig.get(sig)
            if existing_variant:
                # If a matching variant exists but is soft-deleted, revive it instead of creating a new row.
                # This avoids uniqueness errors on `sku` and `(product, signature)`.
                revived = False
                if existing_variant.is_deleted:
                    existing_variant.is_deleted = False
                    existing_variant.deleted_at = None
                    existing_variant.is_active = True

                    # Compatibility: keep legacy `color`/`size` fields populated.
                    for av in attr_values:
                        name = (av.attribute.name or "").strip().lower()
                        if name == "color" and (av.value or "").strip():
                            existing_variant.color = (av.value or "").strip()
                        elif name == "size" and (av.value or "").strip():
                            existing_variant.size = (av.value or "").strip()

                    existing_variant.save(
                        update_fields=["is_deleted", "deleted_at", "is_active", "color", "size", "updated_at"]
                    )

                    # Ensure links match revived signature.
                    existing_variant.variant_attributes.all().delete()
                    VariantAttribute.objects.bulk_create(
                        [
                            VariantAttribute(
                                variant=existing_variant,
                                attribute=av.attribute,
                                attribute_value=av,
                            )
                            for av in attr_values
                        ]
                    )
                    revived = True

                results.append(
                    GeneratedVariantRow(
                        variant=existing_variant,
                        attribute_values=attr_values,
                        created=revived,
                    )
                )
                continue

            # Create new variant.
            sku = sku_for_variant(product=product, attribute_values=attr_values, existing_skus=existing_skus)
            existing_skus.add(sku)

            variant = ProductVariant.objects.create(
                product=product,
                sku=sku,
                signature=sig,
                is_active=True,
            )

            # Compatibility: keep legacy `color`/`size` fields populated when those attributes exist.
            for av in attr_values:
                name = (av.attribute.name or "").strip().lower()
                if name == "color" and (av.value or "").strip():
                    variant.color = (av.value or "").strip()
                elif name == "size" and (av.value or "").strip():
                    variant.size = (av.value or "").strip()
            if variant.color or variant.size:
                variant.save(update_fields=["color", "size", "updated_at"])

            VariantAttribute.objects.bulk_create(
                [
                    VariantAttribute(
                        variant=variant,
                        attribute=av.attribute,
                        attribute_value=av,
                    )
                    for av in attr_values
                ]
            )

            results.append(GeneratedVariantRow(variant=variant, attribute_values=attr_values, created=True))

        if set_first_default_if_none:
            if not ProductVariant.objects.filter(product=product, is_deleted=False, is_default=True).exists():
                # Choose the first variant in the current results (preferring newly-created).
                candidate = next((r.variant for r in results if r.created), None) or (results[0].variant if results else None)
                if candidate:
                    ProductVariant.objects.filter(product=product, is_deleted=False).update(is_default=False)
                    candidate.is_default = True
                    candidate.save(update_fields=["is_default", "updated_at"])

    return results


def preview_variants_for_product(
    *,
    product: Product,
    attribute_value_ids_by_attribute: dict[int, list[int]],
    limit: int = 200,
) -> dict:
    """
    Preview combinations + SKUs without writing to the database.

    Returns:
      {
        "count": <total combinations>,
        "limited": <bool>,
        "rows": [
          {
            "signature": "...",
            "sku": "...",
            "exists": <bool>,
            "variant_id": <int|null>,
            "attribute_values": [AttributeValue, ...]
          },
          ...
        ]
      }
    """
    # Reuse the same validation as the generator.
    cleaned: dict[int, list[int]] = {}
    for attr_id, value_ids in (attribute_value_ids_by_attribute or {}).items():
        attr_id = int(attr_id)
        unique_ids: list[int] = []
        for vid in value_ids or []:
            vid = int(vid)
            if vid not in unique_ids:
                unique_ids.append(vid)
        if unique_ids:
            cleaned[attr_id] = unique_ids

    if not cleaned:
        return {"count": 0, "limited": False, "rows": []}

    all_value_ids = [vid for vids in cleaned.values() for vid in vids]
    values = list(
        AttributeValue.objects.filter(is_deleted=False, is_active=True, id__in=all_value_ids).select_related("attribute")
    )
    value_by_id = {v.id: v for v in values}

    for attr_id, vids in cleaned.items():
        for vid in vids:
            v = value_by_id.get(vid)
            if not v or v.attribute_id != attr_id:
                raise ValueError("Invalid attribute/value selection.")

    attributes = list(
        Attribute.objects.filter(id__in=list(cleaned.keys()), is_deleted=False, is_active=True).order_by("sort_order", "name")
    )
    attr_ids_ordered = [a.id for a in attributes]
    value_lists: list[list[AttributeValue]] = [
        [value_by_id[vid] for vid in cleaned[attr_id]] for attr_id in attr_ids_ordered
    ]

    # Compute total combinations (may be large).
    total = 1
    for lst in value_lists:
        total *= max(1, len(lst))

    # Determine which signatures already exist for this product (dedupe).
    # For preview, we only need existence and maybe the existing variant_id/sku.
    existing_variants = list(
        ProductVariant.objects.filter(product=product, is_deleted=False)
        .exclude(signature__isnull=True)
        .exclude(signature__exact="")
        .only("id", "signature", "sku")
    )
    existing_by_sig = {v.signature: v for v in existing_variants if v.signature}

    existing_skus = set(
        ProductVariant.objects.filter(product=product, is_deleted=False).values_list("sku", flat=True)
    )

    rows = []
    limited = False
    count_added = 0

    for combo in cartesian_product(*value_lists):
        attr_values = list(combo)
        sig = signature_for_pairs([(av.attribute_id, av.id) for av in attr_values])
        existing = existing_by_sig.get(sig)
        if existing:
            sku = existing.sku
            rows.append(
                {
                    "signature": sig,
                    "sku": sku,
                    "exists": True,
                    "variant_id": existing.id,
                    "attribute_values": attr_values,
                }
            )
        else:
            sku = sku_for_variant(product=product, attribute_values=attr_values, existing_skus=existing_skus)
            existing_skus.add(sku)
            rows.append(
                {
                    "signature": sig,
                    "sku": sku,
                    "exists": False,
                    "variant_id": None,
                    "attribute_values": attr_values,
                }
            )

        count_added += 1
        if count_added >= int(limit):
            if total > limit:
                limited = True
            break

    return {"count": total, "limited": limited, "rows": rows}
