from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from apps.products.models import Product

from .models import PromoCode, PromoRedemption


COUPON_SESSION_KEY = "applied_coupon_code"
COUPON_SESSION_AUTO_KEY = "applied_coupon_is_auto"


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def get_applied_coupon_code(request) -> str | None:
    code = normalize_code(str(request.session.get(COUPON_SESSION_KEY) or ""))
    return code or None


def set_applied_coupon_code(request, code: str) -> None:
    request.session[COUPON_SESSION_KEY] = normalize_code(code)
    request.session.modified = True


def get_applied_coupon_is_auto(request) -> bool:
    return bool(request.session.get(COUPON_SESSION_AUTO_KEY, False))


def set_applied_coupon_is_auto(request, is_auto: bool) -> None:
    request.session[COUPON_SESSION_AUTO_KEY] = bool(is_auto)
    request.session.modified = True


def clear_applied_coupon(request) -> None:
    request.session.pop(COUPON_SESSION_KEY, None)
    request.session.pop(COUPON_SESSION_AUTO_KEY, None)
    request.session.modified = True


@dataclass(frozen=True)
class CouponApplication:
    promo: PromoCode | None
    discount_amount: Decimal
    free_shipping: bool
    error: str
    applied_via_auto: bool = False


def _get_applicable_subtotal(*, promo: PromoCode, cart_lines) -> Decimal:
    """
    Returns subtotal of items eligible for coupon (product/category targeting).
    If no targeting configured, entire cart subtotal is eligible.
    """
    applicable_product_ids: set[int] = set(promo.applicable_products.values_list("id", flat=True))
    applicable_category_ids: set[int] = set(promo.applicable_categories.values_list("id", flat=True))

    if not applicable_product_ids and not applicable_category_ids:
        return sum((line.line_total for line in cart_lines), Decimal("0.00"))

    subtotal = Decimal("0.00")
    for line in cart_lines:
        p = line.product
        if p.id in applicable_product_ids:
            subtotal += line.line_total
            continue
        if p.category_id and p.category_id in applicable_category_ids:
            subtotal += line.line_total
            continue
    return subtotal


def _validate_common(*, promo: PromoCode, subtotal: Decimal, user) -> str:
    if not promo.is_currently_active():
        return "Invalid or expired coupon."

    if subtotal < (promo.min_order_amount or Decimal("0.00")):
        return f"Minimum order amount is {promo.min_order_amount}."

    if promo.usage_limit is not None and promo.times_redeemed >= promo.usage_limit:
        return "Coupon usage limit reached."

    if promo.allowed_users.exists():
        if not user or not getattr(user, "is_authenticated", False):
            return "Please login to use this coupon."
        if not promo.allowed_users.filter(id=user.id).exists():
            return "This coupon is not available for your account."

    if promo.one_time_per_user:
        if not user or not getattr(user, "is_authenticated", False):
            return "Please login to use this coupon."
        if PromoRedemption.objects.filter(promo_code=promo, user_id=user.id).exists():
            return "You have already used this coupon."

    return ""


def apply_coupon(
    *,
    code: str,
    cart_lines,
    user,
    allow_auto: bool = False,
) -> CouponApplication:
    code = normalize_code(code)
    if not code:
        return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Enter a coupon code.")

    promo = PromoCode.objects.filter(code=code, is_deleted=False).first()
    if not promo:
        return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Invalid coupon code.")

    subtotal = sum((line.line_total for line in cart_lines), Decimal("0.00"))
    err = _validate_common(promo=promo, subtotal=subtotal, user=user)
    if err:
        return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error=err)

    applicable_subtotal = _get_applicable_subtotal(promo=promo, cart_lines=cart_lines)
    if applicable_subtotal <= 0:
        return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Coupon is not applicable to these products.")

    discount = Decimal("0.00")
    free_shipping = promo.discount_type == PromoCode.DiscountType.FREE_SHIPPING

    if promo.discount_type == PromoCode.DiscountType.PERCENT:
        pct = Decimal(promo.percent_off or 0)
        if pct <= 0:
            return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Coupon is not configured.")
        discount = (applicable_subtotal * pct / Decimal("100")).quantize(Decimal("0.01"))

    elif promo.discount_type == PromoCode.DiscountType.FIXED:
        amt = Decimal(promo.amount_off or 0)
        if amt <= 0:
            return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Coupon is not configured.")
        discount = min(applicable_subtotal, amt).quantize(Decimal("0.01"))

    elif promo.discount_type == PromoCode.DiscountType.BXGY:
        buy_qty = int(promo.bxgy_buy_qty or 0)
        get_qty = int(promo.bxgy_get_qty or 0)
        if buy_qty <= 0 or get_qty <= 0:
            return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Coupon is not configured.")

        # Cheapest-items-free implementation on eligible items.
        # Free qty per group of (buy+get).
        eligible_prices: list[Decimal] = []
        applicable_product_ids: set[int] = set(promo.applicable_products.values_list("id", flat=True))
        applicable_category_ids: set[int] = set(promo.applicable_categories.values_list("id", flat=True))

        def _is_eligible(product: Product) -> bool:
            if not applicable_product_ids and not applicable_category_ids:
                return True
            if product.id in applicable_product_ids:
                return True
            return bool(product.category_id and product.category_id in applicable_category_ids)

        total_eligible_qty = 0
        for line in cart_lines:
            if not _is_eligible(line.product):
                continue
            total_eligible_qty += int(line.quantity)
            eligible_prices.extend([Decimal(line.unit_price)] * int(line.quantity))

        group = buy_qty + get_qty
        free_qty = (total_eligible_qty // group) * get_qty
        if free_qty <= 0:
            discount = Decimal("0.00")
        else:
            eligible_prices.sort()
            discount = sum(eligible_prices[:free_qty], Decimal("0.00")).quantize(Decimal("0.01"))

    else:
        # Free shipping type has no discount amount.
        discount = Decimal("0.00")

    if discount <= 0 and not free_shipping:
        return CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="Coupon does not apply.")

    return CouponApplication(promo=promo, discount_amount=discount, free_shipping=free_shipping, error="", applied_via_auto=allow_auto and promo.auto_apply)


def find_best_auto_coupon(*, cart_lines, user) -> CouponApplication:
    promos = list(
        PromoCode.objects.filter(is_deleted=False, is_active=True, auto_apply=True).order_by("-created_at")[:20]
    )
    best: CouponApplication | None = None
    for promo in promos:
        app = apply_coupon(code=promo.code, cart_lines=cart_lines, user=user, allow_auto=True)
        if app.error:
            continue
        if not best or app.discount_amount > best.discount_amount or (app.free_shipping and not best.free_shipping):
            best = app
    return best or CouponApplication(promo=None, discount_amount=Decimal("0.00"), free_shipping=False, error="")


def record_redemption(
    *,
    promo: PromoCode,
    user,
    order,
    subtotal_amount: Decimal,
    discount_amount: Decimal,
    shipping_amount: Decimal,
    total_amount: Decimal,
    applied_via_auto: bool = False,
) -> PromoRedemption:
    with transaction.atomic():
        promo_locked = PromoCode.objects.select_for_update().filter(id=promo.id, is_deleted=False).first()
        if not promo_locked:
            raise ValueError("Coupon is not available.")

        if not promo_locked.is_currently_active():
            raise ValueError("Coupon is not active.")

        if promo_locked.usage_limit is not None and promo_locked.times_redeemed >= promo_locked.usage_limit:
            raise ValueError("Coupon usage limit reached.")

        if promo_locked.one_time_per_user and user and getattr(user, "is_authenticated", False):
            if PromoRedemption.objects.select_for_update().filter(promo_code_id=promo_locked.id, user_id=user.id).exists():
                raise ValueError("You have already used this coupon.")

        redemption = PromoRedemption.objects.create(
            promo_code=promo_locked,
            user=user if getattr(user, "is_authenticated", False) else None,
            order=order,
            subtotal_amount=subtotal_amount,
            discount_amount=discount_amount,
            shipping_amount=shipping_amount,
            total_amount=total_amount,
            applied_via_auto=applied_via_auto,
        )
        PromoCode.objects.filter(id=promo_locked.id).update(times_redeemed=F("times_redeemed") + 1)
        return redemption
