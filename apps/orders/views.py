from decimal import Decimal, ROUND_HALF_UP

from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.coupons.services import (
    apply_coupon,
    clear_applied_coupon,
    find_best_auto_coupon,
    get_applied_coupon_code,
    get_applied_coupon_is_auto,
    normalize_code,
    set_applied_coupon_code,
    set_applied_coupon_is_auto,
)
from core.utils.settings_loader import get_bool_setting, get_decimal_setting

from .cart import (
    add_to_cart,
    clear_cart,
    get_cart,
    get_cart_lines,
    remove_from_cart,
    set_cart,
)
from .models import Order
from .services import DuplicateOrderError, DUPLICATE_ORDER_ERROR_MESSAGE, create_order_from_products


def cart_view(request):
    lines, total_items, total_amount = get_cart_lines(request)

    free_shipping_enabled = get_bool_setting("shipping.free_enabled", default=True)
    free_shipping_threshold = get_decimal_setting("shipping.free_threshold", default=Decimal("75.00"))
    shipping_fee = get_decimal_setting("shipping.fee", default=Decimal("10.00"))

    # Coupon
    coupon_code = get_applied_coupon_code(request)
    coupon_error = ""
    coupon_app = None

    if coupon_code:
        coupon_app = apply_coupon(code=coupon_code, cart_lines=lines, user=request.user)
        if coupon_app.error:
            coupon_error = coupon_app.error
            clear_applied_coupon(request)
            coupon_code = None
            coupon_app = None

    if not coupon_code:
        auto_app = find_best_auto_coupon(cart_lines=lines, user=request.user)
        if auto_app.promo:
            coupon_app = auto_app
            coupon_code = auto_app.promo.code
            set_applied_coupon_code(request, coupon_code)
            set_applied_coupon_is_auto(request, True)

    discount_amount = (coupon_app.discount_amount if coupon_app and coupon_app.promo else Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    coupon_free_shipping = bool(coupon_app and coupon_app.promo and coupon_app.free_shipping)

    qualifies_for_free_shipping = bool(
        (coupon_free_shipping) or (free_shipping_enabled and total_amount >= free_shipping_threshold)
    )
    shipping_amount = Decimal("0.00") if qualifies_for_free_shipping else shipping_fee

    tax_amount = Decimal("0.00")
    total_with_tax_and_shipping = (total_amount - discount_amount + shipping_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return render(
        request,
        "pages/cart.html",
        {
            "cart_lines": lines,
            "cart_total_items": total_items,
            "cart_total_amount": total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cart_discount_amount": discount_amount,
            "cart_has_discount": bool(discount_amount > 0),
            "cart_coupon_code": coupon_code or "",
            "cart_coupon_error": coupon_error,
            "cart_coupon_free_shipping": coupon_free_shipping,
            "cart_free_shipping_enabled": free_shipping_enabled,
            "cart_free_shipping_threshold": free_shipping_threshold,
            "cart_qualifies_for_free_shipping": qualifies_for_free_shipping,
            "cart_shipping_amount": shipping_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cart_total_with_extras": total_with_tax_and_shipping,
        },
    )


def apply_coupon_ajax(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)

    code = normalize_code(request.POST.get("code") or "")
    lines, total_items, total_amount = get_cart_lines(request)
    app = apply_coupon(code=code, cart_lines=lines, user=request.user)
    if app.error:
        return JsonResponse({"ok": False, "error": app.error}, status=400)

    set_applied_coupon_code(request, code)
    set_applied_coupon_is_auto(request, False)

    free_shipping_enabled = get_bool_setting("shipping.free_enabled", default=True)
    free_shipping_threshold = get_decimal_setting("shipping.free_threshold", default=Decimal("75.00"))
    shipping_fee = get_decimal_setting("shipping.fee", default=Decimal("10.00"))

    qualifies_for_free_shipping = bool(app.free_shipping or (free_shipping_enabled and total_amount >= free_shipping_threshold))
    shipping_amount = Decimal("0.00") if qualifies_for_free_shipping else shipping_fee

    discount_amount = Decimal(app.discount_amount or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (total_amount - discount_amount + shipping_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return JsonResponse(
        {
            "ok": True,
            "code": code,
            "discount_amount": str(discount_amount),
            "shipping_amount": str(shipping_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "total_amount": str(total),
            "free_shipping": bool(app.free_shipping),
        }
    )


def remove_coupon_ajax(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    clear_applied_coupon(request)
    return JsonResponse({"ok": True})


def add_to_cart_view(request, product_public_id: str):
    if request.method == "POST":
        try:
            qty = int(request.POST.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        add_to_cart(request, product_public_id=product_public_id, quantity=max(qty, 1))
    return redirect("orders:cart")


def update_cart_item_view(request, product_public_id: str):
    if request.method == "POST":
        try:
            qty = int(request.POST.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(10, qty))

        cart = get_cart(request)
        if product_public_id in cart:
            cart[product_public_id] = qty
            set_cart(request, cart)
    return redirect("orders:cart")


def remove_from_cart_view(request, product_public_id: str):
    if request.method == "POST":
        remove_from_cart(request, product_public_id=product_public_id)
    return redirect("orders:cart")


def clear_cart_view(request):
    if request.method == "POST":
        clear_cart(request)
    return redirect("orders:cart")


def checkout_view(request):
    lines, total_items, total_amount = get_cart_lines(request)
    if not lines:
        return redirect("orders:cart")

    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?next={reverse('orders:checkout')}")

    free_shipping_enabled = get_bool_setting("shipping.free_enabled", default=True)
    free_shipping_threshold = get_decimal_setting("shipping.free_threshold", default=Decimal("75.00"))
    shipping_fee = get_decimal_setting("shipping.fee", default=Decimal("10.00"))

    coupon_code = get_applied_coupon_code(request)
    coupon_error = ""
    coupon_app = None

    if coupon_code:
        coupon_app = apply_coupon(code=coupon_code, cart_lines=lines, user=request.user)
        if coupon_app.error:
            coupon_error = coupon_app.error
            clear_applied_coupon(request)
            coupon_code = None
            coupon_app = None

    if not coupon_code:
        auto_app = find_best_auto_coupon(cart_lines=lines, user=request.user)
        if auto_app.promo:
            coupon_app = auto_app
            coupon_code = auto_app.promo.code
            set_applied_coupon_code(request, coupon_code)
            set_applied_coupon_is_auto(request, True)

    discount_amount = (coupon_app.discount_amount if coupon_app and coupon_app.promo else Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    coupon_free_shipping = bool(coupon_app and coupon_app.promo and coupon_app.free_shipping)

    qualifies_for_free_shipping = bool(
        coupon_free_shipping or (free_shipping_enabled and total_amount >= free_shipping_threshold)
    )
    shipping_amount = Decimal("0.00") if qualifies_for_free_shipping else shipping_fee
    total_with_shipping = (total_amount - discount_amount + shipping_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    error = ""
    if request.method == "POST":
        note = (request.POST.get("note") or "").strip()
        mobile_number = (request.POST.get("mobile_number") or "").strip()
        cart = get_cart(request)
        coupon_is_auto = get_applied_coupon_is_auto(request)
        try:
            order = create_order_from_products(
                customer=request.user,
                quantities_by_product_public_id=cart,
                mobile_number=mobile_number,
                note=note,
                promo_code=coupon_code,
                promo_applied_via_auto=bool(coupon_is_auto),
            )
            clear_cart(request)
            clear_applied_coupon(request)
            return redirect("orders:tracking", public_id=order.public_id)
        except DuplicateOrderError:
            error = DUPLICATE_ORDER_ERROR_MESSAGE
        except ValueError as exc:
            error = str(exc)

    return render(
        request,
        "pages/checkout.html",
        {
            "cart_lines": lines,
            "cart_total_items": total_items,
            "cart_total_amount": total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cart_coupon_code": coupon_code or "",
            "cart_coupon_error": coupon_error,
            "cart_discount_amount": discount_amount,
            "cart_has_discount": bool(discount_amount > 0),
            "cart_coupon_free_shipping": coupon_free_shipping,
            "cart_free_shipping_threshold": free_shipping_threshold,
            "cart_qualifies_for_free_shipping": qualifies_for_free_shipping,
            "cart_shipping_amount": shipping_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cart_total_with_extras": total_with_shipping,
            "error": error,
        },
    )


def order_history_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?next={reverse('orders:history')}")

    orders = Order.objects.filter(customer=request.user).order_by("-created_at")
    return render(request, "pages/order_history.html", {"orders": orders})


def order_tracking_view(request, public_id: str):
    order = Order.objects.prefetch_related("tracking").select_related("customer").filter(public_id=public_id).first()
    if not order:
        raise Http404("Order not found")

    # If user is authenticated, only allow staff or the owner to see customer-level details.
    can_view_customer_details = (
        request.user.is_authenticated
        and (request.user.is_staff or order.customer_id == request.user.id)
    )

    steps = [
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.DELIVERED,
    ]
    current_step_index = steps.index(order.status) if order.status in steps else -1

    return render(
        request,
        "pages/order_tracking.html",
        {
            "order": order,
            "tracking_events": list(order.tracking.all()),
            "steps": steps,
            "current_step_index": current_step_index,
            "can_view_customer_details": can_view_customer_details,
        },
    )


def track_order_lookup_view(request):
    if request.method == "POST":
        public_id = (request.POST.get("order_id") or "").strip()
        if public_id:
            return redirect("orders:tracking", public_id=public_id)

    return render(request, "pages/track_order_lookup.html")
