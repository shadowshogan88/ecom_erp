from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.products.models import Product


CART_SESSION_KEY = "cart"


def get_cart(request) -> dict[str, int]:
    cart = request.session.get(CART_SESSION_KEY, {})
    if not isinstance(cart, dict):
        cart = {}
    # Ensure all quantities are ints >= 1
    normalized: dict[str, int] = {}
    for k, v in cart.items():
        try:
            qty = int(v)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            normalized[str(k)] = qty
    if normalized != cart:
        request.session[CART_SESSION_KEY] = normalized
    return normalized


def set_cart(request, cart: dict[str, int]) -> None:
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def add_to_cart(request, *, product_public_id: str, quantity: int = 1) -> None:
    cart = get_cart(request)
    cart[product_public_id] = int(cart.get(product_public_id, 0)) + int(quantity)
    if cart[product_public_id] <= 0:
        cart.pop(product_public_id, None)
    set_cart(request, cart)


def remove_from_cart(request, *, product_public_id: str) -> None:
    cart = get_cart(request)
    cart.pop(product_public_id, None)
    set_cart(request, cart)


def clear_cart(request) -> None:
    set_cart(request, {})


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int
    unit_price: Decimal
    line_total: Decimal


def get_cart_lines(request) -> tuple[list[CartLine], int, Decimal]:
    """
    Returns: (lines, total_items, total_amount)
    """
    cart = get_cart(request)
    if not cart:
        return ([], 0, Decimal("0.00"))

    products = list(
        Product.objects.filter(is_active=True, public_id__in=list(cart.keys()))
        .select_related("category")
        .prefetch_related("images")
    )
    products_by_public_id = {p.public_id: p for p in products}

    lines: list[CartLine] = []
    total_items = 0
    total_amount = Decimal("0.00")

    for public_id, quantity in cart.items():
        product = products_by_public_id.get(public_id)
        if not product:
            continue
        qty = int(quantity)
        unit_price = Decimal(product.final_price)
        line_total = unit_price * Decimal(qty)
        lines.append(
            CartLine(
                product=product,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
        total_items += qty
        total_amount += line_total

    return (lines, total_items, total_amount)
