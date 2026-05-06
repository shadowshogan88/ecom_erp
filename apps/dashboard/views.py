from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.inventory.models import InventoryItem, InventoryTransaction, VariantInventoryItem
from apps.orders.models import Order
from apps.orders.invoice import generate_invoice_pdf
from apps.payments.models import Payment, Refund
from apps.products.models import Attribute, AttributeValue, Product, ProductImage, ProductVariant, VariantAttribute
from apps.products.services.variant_generator import generate_variants_for_product, preview_variants_for_product
from apps.shipping.models import Shipment

from .logging import log_admin_action
from .models import Notification
from .forms import (
    AdminProfileForm,
    InventoryAdjustForm,
    PaymentCreateForm,
    ProductForm,
    ProductImageForm,
    ProductVariantForm,
    RefundCreateForm,
    ShipmentUpdateForm,
    SiteContentForm,
)
from .reporting import compute_report_range, generate_orders_report_pdf


def _is_staffish(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or getattr(user, "role", "") in {"admin", "staff"}))


@login_required
@user_passes_test(_is_staffish)
def dashboard_home(request):
    User = get_user_model()
    total_customers = User.objects.filter(is_active=True, role="customer").count()
    total_orders = Order.objects.filter(is_deleted=False).count()
    revenue = (
        Order.objects.filter(is_deleted=False, payment_status=Order.PaymentStatus.PAID)
        .exclude(status=Order.Status.CANCELLED)
        .aggregate(total=Sum("total_amount"))
        .get("total")
        or 0
    )

    recent_orders = (
        Order.objects.filter(is_deleted=False)
        .select_related("customer")
        .order_by("-created_at")[:8]
    )

    unread_notifications = Notification.objects.filter(is_read=False)[:8]

    low_stock = (
        InventoryItem.objects.filter(reorder_level__gt=0, quantity_on_hand__lte=models.F("reorder_level"))
        .select_related("product")
        .order_by("quantity_on_hand")[:8]
    )

    since = timezone.now() - timedelta(days=14)
    series = list(
        Order.objects.filter(is_deleted=False, created_at__gte=since, payment_status=Order.PaymentStatus.PAID)
        .exclude(status=Order.Status.CANCELLED)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(revenue=Sum("total_amount"), orders=Count("id"))
        .order_by("day")
    )
    labels = [row["day"].date().isoformat() for row in series]
    values = [float(row["revenue"] or 0) for row in series]

    return render(
        request,
        "dashboard/home.html",
        {
            "total_customers": total_customers,
            "total_orders": total_orders,
            "total_revenue": revenue,
            "recent_orders": recent_orders,
            "unread_notifications": unread_notifications,
            "low_stock": low_stock,
            "chart_labels_json": json.dumps(labels),
            "chart_values_json": json.dumps(values),
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_logout(request):
    auth_logout(request)
    return redirect("products:home")


@login_required
@user_passes_test(_is_staffish)
def dashboard_profile_edit(request):
    user = request.user

    if request.method == "POST":
        form = AdminProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("dashboard-profile")
    else:
        form = AdminProfileForm(instance=user)

    return render(request, "dashboard/profile_edit.html", {"form": form})


def _parse_date(value: str | None):
    from datetime import date

    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@login_required
@user_passes_test(_is_staffish)
def dashboard_reports(request):
    period = (request.GET.get("period") or "daily").strip().lower()
    start_date = _parse_date(request.GET.get("start_date"))
    end_date = _parse_date(request.GET.get("end_date"))
    report_range = compute_report_range(period=period, start_date=start_date, end_date=end_date)

    qs = (
        Order.objects.filter(is_deleted=False, created_at__gte=report_range.start, created_at__lte=report_range.end)
        .select_related("customer")
        .order_by("-created_at")
    )

    total_count = qs.count()
    total_amount = qs.aggregate(total=Sum("total_amount")).get("total") or 0

    return render(
        request,
        "dashboard/reports.html",
        {
            "orders": qs[:500],
            "period": period,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
            "range_label": report_range.label,
            "total_count": total_count,
            "total_amount": total_amount,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_reports_pdf(request):
    period = (request.GET.get("period") or "daily").strip().lower()
    start_date = _parse_date(request.GET.get("start_date"))
    end_date = _parse_date(request.GET.get("end_date"))
    report_range = compute_report_range(period=period, start_date=start_date, end_date=end_date)

    qs = (
        Order.objects.filter(is_deleted=False, created_at__gte=report_range.start, created_at__lte=report_range.end)
        .select_related("customer")
        .order_by("-created_at")
    )

    rows = []
    for o in qs[:2000]:
        rows.append(
            [
                o.created_at.date().isoformat(),
                o.public_id,
                getattr(o.customer, "username", "") or "",
                str(o.status),
                str(o.payment_status),
                str(o.total_amount),
            ]
        )

    subtitle = f"Range: {report_range.label} | Orders: {qs.count()}"
    pdf = generate_orders_report_pdf(title="Orders Report", subtitle=subtitle, rows=rows)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="orders-report-{period}.pdf"'
    return resp


@login_required
@user_passes_test(_is_staffish)
def dashboard_site_content(request):
    from apps.settings.models import Setting
    from core.utils.settings_loader import get_bool_setting, get_setting

    initial = {
        "banner_enabled": get_bool_setting("site.banner_enabled", default=True),
        "banner_html": get_setting(
            "site.banner_html",
            default=(
                '<div class="bg-gradient-to-r from-primary-600 to-primary-500 py-2 text-center text-sm font-medium text-white">'
                'Free shipping on orders over $75 | Use code <span class="font-bold">STRIDE20</span> for 20% off your first order'
                "</div>"
            ),
        )
        or "",
        "footer_text": get_setting("site.footer_text", default="© 2026 SynckBD. All rights reserved.") or "",
    }

    if request.method == "POST":
        form = SiteContentForm(request.POST)
        if form.is_valid():
            Setting.objects.update_or_create(
                key="site.banner_enabled",
                defaults={"value": "1" if form.cleaned_data.get("banner_enabled") else "0", "description": "Show/hide top banner"},
            )
            Setting.objects.update_or_create(
                key="site.banner_html",
                defaults={"value": form.cleaned_data.get("banner_html") or "", "description": "Top banner HTML"},
            )
            Setting.objects.update_or_create(
                key="site.footer_text",
                defaults={"value": form.cleaned_data.get("footer_text") or "", "description": "Footer copyright text"},
            )
            messages.success(request, "Site content updated.")
            return redirect("dashboard-site-content")
    else:
        form = SiteContentForm(initial=initial)

    return render(request, "dashboard/site_content.html", {"form": form})


@login_required
@user_passes_test(_is_staffish)
def dashboard_orders_list(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    payment_status = (request.GET.get("payment_status") or "").strip()

    qs = Order.objects.filter(is_deleted=False).select_related("customer").order_by("-created_at")
    if q:
        qs = qs.filter(models.Q(public_id__icontains=q) | models.Q(customer__username__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "dashboard/orders_list.html",
        {
            "page_obj": page,
            "q": q,
            "status": status,
            "payment_status": payment_status,
            "status_choices": Order.Status.choices,
            "payment_status_choices": Order.PaymentStatus.choices,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_order_detail(request, public_id: str):
    order_qs = (
        Order.objects.filter(is_deleted=False, public_id=public_id)
        .select_related("customer", "shipment", "shipment__courier", "shipment__zone")
        .prefetch_related("items__product", "tracking", "payments__refunds", "shipment__tracking_events")
    )
    order = order_qs.first()
    if not order:
        return render(request, "dashboard/not_found.html", status=404)

    error = ""
    info = ""
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "order_status":
            new_status = (request.POST.get("status") or "").strip()
            note = (request.POST.get("note") or "").strip()
            if new_status and new_status in dict(Order.Status.choices) and new_status != order.status:
                old = order.status
                order.status = new_status
                order._tracking_note = note or "Status updated"
                order.save(update_fields=["status", "updated_at"])
                log_admin_action(
                    request=request,
                    action="status_change",
                    entity="Order",
                    object_ref=order.public_id,
                    message=f"{old} -> {new_status}",
                    payload={"note": note},
                )
                info = "Order status updated."
            else:
                error = "Invalid order status."

        elif action == "shipment_update":
            shipment = getattr(order, "shipment", None)
            form = ShipmentUpdateForm(request.POST)
            if form.is_valid():
                if not shipment:
                    shipment = Shipment.objects.create(order=order)
                    log_admin_action(
                        request=request,
                        action="create",
                        entity="Shipment",
                        object_ref=order.public_id,
                        message=f"Shipment created for order {order.public_id}",
                    )

                update_fields: list[str] = ["updated_at"]

                courier = form.cleaned_data.get("courier")
                zone = form.cleaned_data.get("zone")
                tracking_number = (form.cleaned_data.get("tracking_number") or "").strip()
                shipping_cost = form.cleaned_data.get("shipping_cost")
                note = (form.cleaned_data.get("note") or "").strip()
                new_status = form.cleaned_data.get("status")
                status_changed = bool(new_status and new_status != shipment.status)

                if courier != shipment.courier:
                    shipment.courier = courier
                    update_fields.append("courier")
                if zone != shipment.zone:
                    shipment.zone = zone
                    update_fields.append("zone")
                if tracking_number != (shipment.tracking_number or ""):
                    shipment.tracking_number = tracking_number
                    update_fields.append("tracking_number")
                if shipping_cost is not None and shipping_cost != shipment.shipping_cost:
                    shipment.shipping_cost = shipping_cost
                    update_fields.append("shipping_cost")
                if note and not status_changed:
                    shipment.note = (shipment.note or "").strip() + ("\n" if shipment.note else "") + note
                    update_fields.append("note")

                if len(update_fields) > 1:
                    shipment.save(update_fields=update_fields)

                if status_changed:
                    old = shipment.status
                    shipment.set_status(status=new_status, note=note or "Status updated")
                    log_admin_action(
                        request=request,
                        action="status_change",
                        entity="Shipment",
                        object_ref=order.public_id,
                        message=f"{old} -> {new_status}",
                        payload={"note": note},
                    )
                info = "Shipment updated."
            else:
                error = "Invalid shipment data."

        elif action == "payment_create":
            form = PaymentCreateForm(request.POST)
            if form.is_valid():
                payment = Payment.objects.create(
                    order=order,
                    customer=order.customer,
                    method=form.cleaned_data["method"],
                    status=form.cleaned_data["status"],
                    amount=form.cleaned_data["amount"],
                    transaction_id=(form.cleaned_data.get("transaction_id") or "").strip(),
                    note=(form.cleaned_data.get("note") or "").strip(),
                    created_by=request.user,
                )
                log_admin_action(
                    request=request,
                    action="create",
                    entity="Payment",
                    object_ref=payment.public_id,
                    message=f"Payment created for order {order.public_id}",
                )
                info = "Payment created."
            else:
                error = "Invalid payment data."

        elif action == "refund_create":
            payment_public_id = (request.POST.get("payment_public_id") or "").strip()
            payment = order.payments.filter(public_id=payment_public_id).first()
            if not payment:
                error = "Payment not found for this order."
            else:
                form = RefundCreateForm(request.POST)
                if form.is_valid():
                    refund = Refund.objects.create(
                        payment=payment,
                        status=Refund.Status.REQUESTED,
                        amount=form.cleaned_data["amount"],
                        reason=(form.cleaned_data.get("reason") or "").strip(),
                        created_by=request.user,
                    )
                    payment.status = Payment.Status.REFUNDED
                    payment.save(update_fields=["status", "updated_at"])
                    log_admin_action(
                        request=request,
                        action="create",
                        entity="Refund",
                        object_ref=str(refund.id),
                        message=f"Refund created for payment {payment.public_id}",
                    )
                    info = "Refund created."
                else:
                    error = "Invalid refund data."

        else:
            error = "Unknown action."

    order = order_qs.first()
    return render(
        request,
        "dashboard/order_detail.html",
        {
            "order": order,
            "items": list(order.items.filter(is_deleted=False).select_related("product")),
            "tracking_events": list(order.tracking.all()),
            "shipment": getattr(order, "shipment", None),
            "shipment_events": list(getattr(getattr(order, "shipment", None), "tracking_events", []).all())
            if getattr(order, "shipment", None)
            else [],
            "payments": list(order.payments.all().prefetch_related("refunds")),
            "shipment_form": ShipmentUpdateForm(
                initial={
                    "status": getattr(getattr(order, "shipment", None), "status", Shipment.Status.PENDING),
                    "tracking_number": getattr(getattr(order, "shipment", None), "tracking_number", ""),
                    "courier": getattr(getattr(order, "shipment", None), "courier", None),
                    "zone": getattr(getattr(order, "shipment", None), "zone", None),
                    "shipping_cost": getattr(getattr(order, "shipment", None), "shipping_cost", None),
                }
            ),
            "payment_form": PaymentCreateForm(initial={"amount": order.total_amount}),
            "status_choices": Order.Status.choices,
            "error": error,
            "info": info,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_order_invoice_pdf(request, public_id: str):
    order = (
        Order.objects.filter(is_deleted=False, public_id=public_id)
        .select_related("customer")
        .prefetch_related("items__product")
        .first()
    )
    if not order:
        return render(request, "dashboard/not_found.html", status=404)

    pdf = generate_invoice_pdf(order=order)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="invoice-{order.public_id}.pdf"'
    return resp


@login_required
@user_passes_test(_is_staffish)
def dashboard_products_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Product.objects.all().select_related("category", "inventory_item").order_by("-created_at")
    if q:
        qs = qs.filter(models.Q(name__icontains=q) | models.Q(public_id__icontains=q))

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "dashboard/products_list.html",
        {"page_obj": page, "q": q},
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product: Product = form.save()
        log_admin_action(
            request=request,
            action="create",
            entity="Product",
            object_ref=product.public_id,
            message=f"Product created: {product.name}",
        )
        return redirect("dashboard-product-edit", public_id=product.public_id)

    return render(request, "dashboard/product_form.html", {"form": form, "product": None, "is_create": True})


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_edit(request, public_id: str):
    product_qs = (
        Product.objects.filter(public_id=public_id)
        .select_related("category", "inventory_item")
        .prefetch_related("variants", "images")
    )
    product = product_qs.first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        updated: Product = form.save()
        log_admin_action(
            request=request,
            action="update",
            entity="Product",
            object_ref=updated.public_id,
            message="Product updated",
        )
        return redirect("dashboard-product-edit", public_id=updated.public_id)

    product = product_qs.first()
    inv = getattr(product, "inventory_item", None)
    inventory_form = InventoryAdjustForm(instance=inv) if inv else None

    return render(
        request,
        "dashboard/product_form.html",
        {
            "form": form,
            "product": product,
            "is_create": False,
            "inventory_form": inventory_form,
            "variants": list(product.variants.filter(is_deleted=False).order_by("sku")),
            "images": list(product.images.all().order_by("sort_order", "id")),
        },
    )


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_product_delete(request, public_id: str):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    name = product.name
    product.delete()
    log_admin_action(
        request=request,
        action="delete",
        entity="Product",
        object_ref=product.public_id,
        message=f"Product deleted: {name}",
    )
    return redirect("dashboard-products")


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_product_inventory_update(request, public_id: str):
    product = Product.objects.filter(public_id=public_id).select_related("inventory_item").first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    inv = getattr(product, "inventory_item", None)
    if not inv:
        inv = InventoryItem.objects.create(product=product)

    old_qty = int(inv.quantity_on_hand or 0)
    form = InventoryAdjustForm(request.POST, instance=inv)
    if form.is_valid():
        inv = form.save(commit=False)
        new_qty = int(inv.quantity_on_hand or 0)
        delta = new_qty - old_qty

        inv.last_counted_at = timezone.now()
        inv.save(update_fields=["quantity_on_hand", "reorder_level", "last_counted_at", "updated_at"])

        if delta != 0:
            InventoryTransaction.objects.create(
                product=product,
                txn_type=InventoryTransaction.TxnType.ADJUSTMENT,
                quantity_delta=delta,
                note=f"Manual adjustment via dashboard by {request.user.username}",
            )
            log_admin_action(
                request=request,
                action="update",
                entity="Inventory",
                object_ref=product.public_id,
                message=f"Stock adjusted by {delta}",
            )

    return redirect("dashboard-product-edit", public_id=product.public_id)


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_variant_create(request, public_id: str):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    form = ProductVariantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        variant: ProductVariant = form.save(commit=False)
        variant.product = product
        variant.save()
        log_admin_action(
            request=request,
            action="create",
            entity="ProductVariant",
            object_ref=str(variant.id),
            message=f"Variant created for {product.public_id}",
        )
        return redirect("dashboard-product-edit", public_id=product.public_id)

    return render(request, "dashboard/product_variant_form.html", {"form": form, "product": product, "variant": None})


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_variant_edit(request, public_id: str, variant_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    # Soft-delete aware: allow editing a previously deleted variant by restoring it.
    # This avoids confusing "Not found" errors when an admin clicks an older link.
    variant = ProductVariant.all_objects.filter(product=product, id=variant_id).first()
    if not variant:
        return render(request, "dashboard/not_found.html", status=404)

    if variant.is_deleted:
        variant.is_deleted = False
        variant.deleted_at = None
        variant.is_active = True
        variant.save(update_fields=["is_deleted", "deleted_at", "is_active"])
        log_admin_action(
            request=request,
            action="restore",
            entity="ProductVariant",
            object_ref=str(variant.id),
            message="Variant restored via edit",
        )

    form = ProductVariantForm(request.POST or None, instance=variant)
    if request.method == "POST" and form.is_valid():
        variant = form.save()
        log_admin_action(
            request=request,
            action="update",
            entity="ProductVariant",
            object_ref=str(variant.id),
            message="Variant updated",
        )
        return redirect("dashboard-product-edit", public_id=product.public_id)

    return render(request, "dashboard/product_variant_form.html", {"form": form, "product": product, "variant": variant})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_product_variant_delete(request, public_id: str, variant_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    # Soft-delete aware: treat "delete again" as an idempotent operation.
    variant = ProductVariant.all_objects.filter(product=product, id=variant_id).first()
    if not variant:
        return render(request, "dashboard/not_found.html", status=404)

    if variant.is_deleted:
        return redirect("dashboard-product-edit", public_id=product.public_id)

    variant.delete()
    log_admin_action(
        request=request,
        action="delete",
        entity="ProductVariant",
        object_ref=str(variant.id),
        message=f"Variant deleted for {product.public_id}",
    )
    return redirect("dashboard-product-edit", public_id=product.public_id)


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_image_create(request, public_id: str):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    form = ProductImageForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        img: ProductImage = form.save(commit=False)
        img.product = product
        img.save()

        if img.is_primary:
            ProductImage.objects.filter(product=product).exclude(id=img.id).update(is_primary=False)

        log_admin_action(
            request=request,
            action="create",
            entity="ProductImage",
            object_ref=str(img.id),
            message=f"Image added for {product.public_id}",
        )
        return redirect("dashboard-product-edit", public_id=product.public_id)

    return render(request, "dashboard/product_image_form.html", {"form": form, "product": product})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_product_image_delete(request, public_id: str, image_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    img = ProductImage.objects.filter(product=product, id=image_id).first()
    if not img:
        return render(request, "dashboard/not_found.html", status=404)

    img.delete()
    log_admin_action(
        request=request,
        action="delete",
        entity="ProductImage",
        object_ref=str(image_id),
        message=f"Image deleted for {product.public_id}",
    )
    return redirect("dashboard-product-edit", public_id=product.public_id)


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_product_image_make_primary(request, public_id: str, image_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    img = ProductImage.objects.filter(product=product, id=image_id).first()
    if not img:
        return render(request, "dashboard/not_found.html", status=404)

    ProductImage.objects.filter(product=product).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=["is_primary", "updated_at"])
    log_admin_action(
        request=request,
        action="update",
        entity="ProductImage",
        object_ref=str(img.id),
        message="Primary image set",
    )
    return redirect("dashboard-product-edit", public_id=product.public_id)


@login_required
@user_passes_test(_is_staffish)
def dashboard_inventory_list(request):
    q = (request.GET.get("q") or "").strip()
    low_stock_only = (request.GET.get("low_stock") or "").strip() in {"1", "true", "yes", "on"}

    qs = InventoryItem.objects.select_related("product", "product__category").order_by(
        "quantity_on_hand", "product__name"
    )
    if q:
        qs = qs.filter(
            models.Q(product__name__icontains=q)
            | models.Q(product__public_id__icontains=q)
            | models.Q(product__slug__icontains=q)
        )
    if low_stock_only:
        qs = qs.filter(reorder_level__gt=0, quantity_on_hand__lte=models.F("reorder_level"))

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "dashboard/inventory_list.html",
        {"page_obj": page, "q": q, "low_stock": low_stock_only},
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_customers_list(request):
    User = get_user_model()

    q = (request.GET.get("q") or "").strip()

    qs = User.objects.filter(is_active=True, role="customer").order_by("-date_joined")
    if q:
        qs = qs.filter(
            models.Q(username__icontains=q)
            | models.Q(email__icontains=q)
            | models.Q(public_id__icontains=q)
        )

    qs = qs.annotate(
        orders_count=Count("orders", filter=models.Q(orders__is_deleted=False), distinct=True),
        total_spent=Sum(
            "orders__total_amount",
            filter=models.Q(
                orders__is_deleted=False,
                orders__payment_status=Order.PaymentStatus.PAID,
            )
            & ~models.Q(orders__status=Order.Status.CANCELLED),
        ),
    )

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "dashboard/customers_list.html",
        {"page_obj": page, "q": q},
    )


# ---------------------------------------------------------------------------
# Attribute + Variant Generator (AJAX) - ERP Product Management
# ---------------------------------------------------------------------------


def _json_error(detail: str, *, status: int = 400, **extra):
    payload = {"detail": detail}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json_body(request):
    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw or "{}")
    except Exception:
        return None


def _serialize_attribute_value(v: AttributeValue):
    return {
        "id": v.id,
        "attribute_id": v.attribute_id,
        "attribute_name": getattr(v.attribute, "name", ""),
        "attribute_type": getattr(v.attribute, "attribute_type", ""),
        "value": v.value,
        "color_code": v.color_code or "",
        "image_url": v.image.url if getattr(v, "image", None) else "",
    }


def _serialize_variant(v: ProductVariant):
    inv = getattr(v, "inventory_item", None)
    return {
        "id": v.id,
        "sku": v.sku,
        "price_override": str(v.price_override) if v.price_override is not None else "",
        "is_default": bool(v.is_default),
        "is_active": bool(v.is_active),
        "size": v.size or "",
        "color": v.color or "",
        "image_url": v.image.url if getattr(v, "image", None) else "",
        "stock": int(getattr(inv, "quantity_on_hand", 0) or 0),
    }


@login_required
@user_passes_test(_is_staffish)
def dashboard_product_variant_generator(request, public_id: str):
    """
    ERP-style Product Variant generator UI (Bootstrap + Vanilla JS).

    This page lets staff:
      - pick AttributeValues (tag-based)
      - generate all combinations
      - bulk edit price/stock
      - set a single default variant
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return render(request, "dashboard/not_found.html", status=404)

    attributes = list(
        Attribute.objects.filter(is_deleted=False, is_active=True)
        .prefetch_related("values")
        .order_by("sort_order", "name")
    )

    return render(
        request,
        "dashboard/product_variant_generator.html",
        {
            "product": product,
            "attributes": attributes,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_attributes_list(request):
    """
    Attribute management UI (CRUD-lite).

    Staff can create Attributes here and drill into values management.
    """
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        attribute_type = (request.POST.get("attribute_type") or Attribute.Type.TEXT).strip()
        sort_order = int(request.POST.get("sort_order") or 0)
        is_active = (request.POST.get("is_active") or "") in {"1", "true", "on", "yes"}

        if not name:
            return render(
                request,
                "dashboard/attributes_list.html",
                {
                    "attributes": list(Attribute.objects.filter(is_deleted=False).order_by("sort_order", "name")),
                    "error": "Name is required.",
                },
                status=400,
            )

        obj = Attribute.objects.create(
            name=name,
            attribute_type=attribute_type if attribute_type in {Attribute.Type.TEXT, Attribute.Type.COLOR} else Attribute.Type.TEXT,
            sort_order=sort_order,
            is_active=is_active,
        )
        log_admin_action(
            request=request,
            action="create",
            entity="Attribute",
            object_ref=str(obj.id),
            message=f"Attribute created: {obj.name}",
        )
        return redirect("dashboard-attributes")

    attributes = list(Attribute.objects.filter(is_deleted=False).order_by("sort_order", "name"))
    return render(request, "dashboard/attributes_list.html", {"attributes": attributes})


@login_required
@user_passes_test(_is_staffish)
def dashboard_attribute_values_manage(request, attribute_id: int):
    """
    Attribute values management UI.

    Value creation is expected to happen via AJAX (tag-like input),
    while deletion uses a simple POST (safe + CSRF-protected).
    """
    attribute = Attribute.objects.filter(is_deleted=False, id=attribute_id).first()
    if not attribute:
        return render(request, "dashboard/not_found.html", status=404)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "delete_value":
            value_id = int(request.POST.get("value_id") or 0)
            v = AttributeValue.objects.filter(attribute=attribute, id=value_id).first()
            if v:
                v.delete()
                log_admin_action(
                    request=request,
                    action="delete",
                    entity="AttributeValue",
                    object_ref=str(v.id),
                    message=f"Deleted value '{v.value}' from {attribute.name}",
                )
        elif action == "update_attribute":
            attribute.name = (request.POST.get("name") or attribute.name).strip() or attribute.name
            attribute.attribute_type = (
                (request.POST.get("attribute_type") or attribute.attribute_type).strip() or attribute.attribute_type
            )
            attribute.sort_order = int(request.POST.get("sort_order") or attribute.sort_order or 0)
            attribute.is_active = (request.POST.get("is_active") or "") in {"1", "true", "on", "yes"}
            attribute.save(update_fields=["name", "attribute_type", "sort_order", "is_active", "updated_at"])
            log_admin_action(
                request=request,
                action="update",
                entity="Attribute",
                object_ref=str(attribute.id),
                message="Attribute updated",
            )
        elif action == "delete_attribute":
            name = attribute.name
            attribute.delete()
            log_admin_action(
                request=request,
                action="delete",
                entity="Attribute",
                object_ref=str(attribute.id),
                message=f"Attribute deleted: {name}",
            )
            return redirect("dashboard-attributes")

        return redirect("dashboard-attribute-values", attribute_id=attribute.id)

    values = list(AttributeValue.objects.filter(attribute=attribute).order_by("sort_order", "value"))
    return render(
        request,
        "dashboard/attribute_values.html",
        {"attribute": attribute, "values": values},
    )


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_attribute_value_create(request, attribute_id: int):
    """
    AJAX endpoint used by the tag-based UI to create an AttributeValue on the fly.

    Accepts multipart/form-data (supports optional image upload).
    """
    attribute = Attribute.objects.filter(is_deleted=False, id=attribute_id).first()
    if not attribute:
        return _json_error("Attribute not found.", status=404)

    value = (request.POST.get("value") or "").strip()
    if not value:
        return _json_error("Value is required.")

    color_code = (request.POST.get("color_code") or "").strip()
    if attribute.attribute_type != Attribute.Type.COLOR:
        color_code = ""

    if color_code and not color_code.startswith("#"):
        return _json_error("Color code must be a hex like #FF0000.")
    if color_code and len(color_code) not in {4, 7}:
        return _json_error("Color code must be a short or long hex like #FFF or #FFFFFF.")

    image = request.FILES.get("image")

    # Soft-delete aware upsert: reuse existing (even if deleted) to prevent duplicates.
    existing = AttributeValue.all_objects.filter(attribute=attribute, value__iexact=value).select_related("attribute").first()
    if existing and existing.is_deleted:
        existing.is_deleted = False
        existing.deleted_at = None
        existing.is_active = True
        if color_code:
            existing.color_code = color_code
        if image:
            existing.image = image
        existing.save(update_fields=["is_deleted", "deleted_at", "is_active", "color_code", "image", "updated_at"])
        return JsonResponse({"created": False, "value": _serialize_attribute_value(existing)})

    if existing and not existing.is_deleted:
        # Optional: update extra fields if user provided them.
        changed_fields: list[str] = []
        if color_code and color_code != (existing.color_code or ""):
            existing.color_code = color_code
            changed_fields.append("color_code")
        if image:
            existing.image = image
            changed_fields.append("image")
        if changed_fields:
            changed_fields.append("updated_at")
            existing.save(update_fields=changed_fields)
        return JsonResponse({"created": False, "value": _serialize_attribute_value(existing)})

    obj = AttributeValue.objects.create(
        attribute=attribute,
        value=value,
        color_code=color_code,
        image=image if image else None,
        is_active=True,
    )
    obj = AttributeValue.objects.filter(id=obj.id).select_related("attribute").first()
    return JsonResponse({"created": True, "value": _serialize_attribute_value(obj)})


@login_required
@user_passes_test(_is_staffish)
def dashboard_api_product_variants_data(request, public_id: str):
    """
    GET: returns existing variants + their attribute values for the generator UI.
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    variants = list(
        ProductVariant.objects.filter(product=product, is_deleted=False)
        .select_related("inventory_item")
        .prefetch_related("variant_attributes__attribute", "variant_attributes__attribute_value")
        .order_by("sku")
    )

    rows = []
    for v in variants:
        attrs = []
        for link in v.variant_attributes.all():
            av = link.attribute_value
            av.attribute = link.attribute  # Ensure attribute is present for serialization
            attrs.append(_serialize_attribute_value(av))
        rows.append({"variant": _serialize_variant(v), "attributes": attrs})

    return JsonResponse({"product_public_id": product.public_id, "rows": rows})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_generate_variants(request, public_id: str):
    """
    POST JSON:
      {
        "attribute_values": { "<attribute_id>": [<value_id>, ...], ... }
      }

    Generates combinations and returns the full, refreshed variants table (JSON).
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    body = _parse_json_body(request)
    if body is None:
        return _json_error("Invalid JSON body.")

    mapping = body.get("attribute_values") or {}
    try:
        results = generate_variants_for_product(product=product, attribute_value_ids_by_attribute=mapping)
    except ValueError as e:
        return _json_error(str(e) or "Invalid selection.")
    except Exception:
        return _json_error("Variant generation failed. Please review your attributes/values and try again.")

    created_count = sum(1 for r in results if r.created)

    # Return fresh rows for UI rendering.
    return JsonResponse(
        {
            "created_count": created_count,
            "total_generated": len(results),
        }
    )


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_preview_variants(request, public_id: str):
    """
    POST JSON:
      { "attribute_values": { "<attribute_id>": [<value_id>, ...], ... } }

    Returns a limited preview list of combinations + SKUs (no DB writes).
    Useful for "real-time SKU preview" UX.
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    body = _parse_json_body(request)
    if body is None:
        return _json_error("Invalid JSON body.")

    mapping = body.get("attribute_values") or {}
    try:
        preview = preview_variants_for_product(product=product, attribute_value_ids_by_attribute=mapping, limit=200)
    except ValueError as e:
        return _json_error(str(e) or "Invalid selection.")
    except Exception:
        return _json_error("Preview failed. Please try again.")

    rows = []
    for row in preview.get("rows", []):
        attrs = row.get("attribute_values") or []
        rows.append(
            {
                "signature": row.get("signature") or "",
                "sku": row.get("sku") or "",
                "exists": bool(row.get("exists")),
                "variant_id": row.get("variant_id"),
                "attributes": [_serialize_attribute_value(av) for av in attrs],
            }
        )

    return JsonResponse(
        {
            "count": int(preview.get("count") or 0),
            "limited": bool(preview.get("limited")),
            "rows": rows,
        }
    )


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_variant_bulk_update(request, public_id: str):
    """
    Bulk update endpoint (AJAX).

    POST JSON:
      {
        "variant_ids": [1,2,3],
        "price_override": "1999.00" | "" | null,
        "stock": 50 | null
      }
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    body = _parse_json_body(request)
    if body is None:
        return _json_error("Invalid JSON body.")

    variant_ids = body.get("variant_ids") or []
    if not isinstance(variant_ids, list) or not variant_ids:
        return _json_error("variant_ids must be a non-empty list.")

    # Parse price_override (optional)
    price_override_raw = body.get("price_override", None)
    price_override: Decimal | None = None
    if price_override_raw not in (None, ""):
        try:
            price_override = Decimal(str(price_override_raw))
            if price_override < 0:
                return _json_error("Price cannot be negative.")
        except Exception:
            return _json_error("Invalid price_override.")

    # Parse stock (optional). If the key is present with `null`, treat as "no change".
    stock: int | None = None
    update_stock = "stock" in body and body.get("stock", None) is not None
    if update_stock:
        stock_raw = body.get("stock")
        try:
            stock = int(stock_raw)
        except Exception:
            return _json_error("Invalid stock.")
        if stock < 0:
            return _json_error("Stock cannot be negative.")

    qs = ProductVariant.objects.filter(product=product, is_deleted=False, id__in=variant_ids).select_related("inventory_item")
    found_ids = set(qs.values_list("id", flat=True))
    missing = [vid for vid in variant_ids if vid not in found_ids]
    if missing:
        return _json_error("Some variants were not found for this product.", missing_ids=missing)

    updated = 0
    update_price = "price_override" in body

    for v in qs:
        update_fields: list[str] = ["updated_at"]
        if update_price:
            v.price_override = price_override
            update_fields.append("price_override")

        if update_stock:
            inv = getattr(v, "inventory_item", None)
            if not inv:
                inv = VariantInventoryItem.objects.create(variant=v)
            inv.quantity_on_hand = int(stock or 0)
            inv.save(update_fields=["quantity_on_hand", "updated_at"])

        v.save(update_fields=update_fields)
        updated += 1

    return JsonResponse({"updated": updated})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_variant_set_default(request, public_id: str, variant_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    variant = ProductVariant.objects.filter(product=product, id=variant_id, is_deleted=False).first()
    if not variant:
        return _json_error("Variant not found.", status=404)

    ProductVariant.objects.filter(product=product, is_deleted=False).update(is_default=False)
    variant.is_default = True
    variant.save(update_fields=["is_default", "updated_at"])

    return JsonResponse({"default_variant_id": variant.id})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_variant_delete(request, public_id: str, variant_id: int):
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    variant = ProductVariant.objects.filter(product=product, id=variant_id, is_deleted=False).first()
    if not variant:
        return _json_error("Variant not found.", status=404)

    was_default = bool(variant.is_default)
    variant.delete()

    new_default_id = None
    if was_default:
        replacement = (
            ProductVariant.objects.filter(product=product, is_deleted=False)
            .order_by("id")
            .first()
        )
        if replacement:
            ProductVariant.objects.filter(product=product, is_deleted=False).update(is_default=False)
            replacement.is_default = True
            replacement.save(update_fields=["is_default", "updated_at"])
            new_default_id = replacement.id

    return JsonResponse({"deleted": True, "variant_id": variant.id, "new_default_id": new_default_id})


@login_required
@user_passes_test(_is_staffish)
@require_POST
def dashboard_api_variant_image_upload(request, public_id: str, variant_id: int):
    """
    Upload a per-variant image (AJAX multipart/form-data).
    """
    product = Product.objects.filter(public_id=public_id).first()
    if not product:
        return _json_error("Product not found.", status=404)

    variant = ProductVariant.objects.filter(product=product, id=variant_id, is_deleted=False).first()
    if not variant:
        return _json_error("Variant not found.", status=404)

    image = request.FILES.get("image")
    if not image:
        return _json_error("Image is required.")

    variant.image = image
    variant.save(update_fields=["image", "updated_at"])
    return JsonResponse({"variant_id": variant.id, "image_url": variant.image.url if variant.image else ""})
