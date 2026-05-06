from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.utils.settings_loader import get_bool_setting, get_int_setting

from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.products.models import Product

from .models import Order, OrderItem


DUPLICATE_ORDER_ERROR_MESSAGE = "You have already ordered this product within restricted time"


class DuplicateOrderError(Exception):
    pass


def enforce_duplicate_order_restriction(*, customer, product_ids: list[int]) -> None:
    """
    Duplicate Order Defense System:
      - If enabled (db setting `duplicate_order_enabled`):
          Block if the same customer ordered any of the same products in the last X days
          where X is `duplicate_order_days`
      - Cancelled orders are ignored
    """

    if not customer or not getattr(customer, "is_authenticated", False):
        return

    enabled = get_bool_setting("duplicate_order_enabled", default=False)
    if not enabled:
        return

    days = get_int_setting("duplicate_order_days", default=0)
    if days <= 0:
        return

    if not product_ids:
        return

    since = timezone.now() - timedelta(days=days)

    restricted_statuses = [
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.DELIVERED,
    ]

    duplicate_exists = (
        OrderItem.objects.filter(
            order__customer=customer,
            order__is_deleted=False,
            order__status__in=restricted_statuses,
            order__created_at__gte=since,
            product_id__in=product_ids,
        )
        .only("id")
        .exists()
    )

    if duplicate_exists:
        raise DuplicateOrderError(DUPLICATE_ORDER_ERROR_MESSAGE)


def create_order_from_products(
    *,
    customer,
    quantities_by_product_public_id: dict[str, int],
    mobile_number: str,
    note: str = "",
) -> Order:
    """
    Creates an order and items from a mapping of Product.public_id -> quantity.

    Enforces duplicate-order restriction if enabled.
    """

    if not customer or not getattr(customer, "is_authenticated", False):
        raise ValueError("Authenticated customer is required.")

    if not quantities_by_product_public_id:
        raise ValueError("At least one product is required.")

    mobile_number = (mobile_number or "").strip()
    if not mobile_number:
        raise ValueError("Mobile number is required.")

    products = list(
        Product.objects.filter(
            is_active=True, public_id__in=list(quantities_by_product_public_id.keys())
        ).only("id", "public_id", "price", "discount_type", "discount_value")
    )
    products_by_public_id = {p.public_id: p for p in products}

    missing = sorted(set(quantities_by_product_public_id.keys()) - set(products_by_public_id.keys()))
    if missing:
        raise ValueError(f"Unknown products: {', '.join(missing)}")

    product_ids = [p.id for p in products]
    enforce_duplicate_order_restriction(customer=customer, product_ids=product_ids)

    with transaction.atomic():
        inventory_items = list(
            InventoryItem.objects.select_for_update()
            .filter(product_id__in=product_ids)
            .only("id", "product_id", "quantity_on_hand")
        )
        inventory_by_product_id = {i.product_id: i for i in inventory_items}

        for product_public_id, quantity in quantities_by_product_public_id.items():
            product = products_by_public_id[product_public_id]
            qty = int(quantity)
            inv = inventory_by_product_id.get(product.id)
            if inv and inv.quantity_on_hand < qty:
                raise ValueError(f"Insufficient stock for {product.name}. Available: {inv.quantity_on_hand}")

        order = Order(customer=customer, mobile_number=mobile_number, note=note)
        order._tracking_note = "Order placed"
        order.save()

        items: list[OrderItem] = []
        for product_public_id, quantity in quantities_by_product_public_id.items():
            product = products_by_public_id[product_public_id]
            unit_price = product.final_price
            qty = int(quantity)
            items.append(
                OrderItem(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=unit_price * qty,
                )
            )
        OrderItem.objects.bulk_create(items)
        order.recalculate_totals(save=True)

        # Inventory auto-update
        for item in items:
            inv = inventory_by_product_id.get(item.product_id)
            if not inv:
                continue
            inv.quantity_on_hand = int(inv.quantity_on_hand) - int(item.quantity)
            inv.save(update_fields=["quantity_on_hand", "updated_at"])
            InventoryTransaction.objects.create(
                product_id=item.product_id,
                txn_type=InventoryTransaction.TxnType.SALE,
                quantity_delta=-int(item.quantity),
                note=f"Sale for order {order.public_id}",
                order=order,
            )
        return order
