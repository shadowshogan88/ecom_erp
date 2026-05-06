from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.coupons.models import PromoCode, PromoRedemption
from apps.products.models import Category, Product


def _is_staffish(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or getattr(user, "role", "") in {"admin", "staff"}))


class PromoCodeFormMixin:
    """
    Simple bootstrap-ish form fields without adding a new dependency.
    """

    def _bootstrap(self):
        for _, field in self.fields.items():
            widget = field.widget
            css = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = (css + " form-check-input").strip()
                continue

            if isinstance(widget, forms.Select):
                widget.attrs["class"] = (css + " form-select").strip()
                continue

            widget.attrs["class"] = (css + " form-control").strip()


class PromoCodeForm(PromoCodeFormMixin, forms.ModelForm):
    allowed_users = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.filter(is_active=True).order_by("username"),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Optional. If set, only these users can apply.",
    )
    applicable_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Optional. If empty, applies to all products.",
    )
    applicable_categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Optional. If empty, applies to all categories.",
    )

    class Meta:
        model = PromoCode
        fields = [
            "code",
            "name",
            "description",
            "discount_type",
            "percent_off",
            "amount_off",
            "bxgy_buy_qty",
            "bxgy_get_qty",
            "is_active",
            "auto_apply",
            "starts_at",
            "ends_at",
            "min_order_amount",
            "one_time_per_user",
            "usage_limit",
            "allowed_users",
            "applicable_products",
            "applicable_categories",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HTML `datetime-local` format
        for name in ("starts_at", "ends_at"):
            if name in self.fields:
                self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self._bootstrap()


@login_required
@user_passes_test(_is_staffish)
def dashboard_coupons_list(request):
    q = (request.GET.get("q") or "").strip()
    discount_type = (request.GET.get("discount_type") or "").strip()
    is_active = (request.GET.get("is_active") or "").strip()
    auto_apply = (request.GET.get("auto_apply") or "").strip()

    qs = PromoCode.all_objects.select_related().order_by("-created_at")
    if q:
        qs = qs.filter(models.Q(code__icontains=q) | models.Q(name__icontains=q))
    if discount_type:
        qs = qs.filter(discount_type=discount_type)
    if is_active in {"0", "1"}:
        qs = qs.filter(is_active=(is_active == "1"))
    if auto_apply in {"0", "1"}:
        qs = qs.filter(auto_apply=(auto_apply == "1"))

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)
    qs_params = request.GET.copy()
    qs_params.pop("page", None)
    querystring = qs_params.urlencode()

    return render(
        request,
        "dashboard/coupons_list.html",
        {
            "page_obj": page,
            "q": q,
            "discount_type": discount_type,
            "is_active": is_active,
            "auto_apply": auto_apply,
            "discount_type_choices": PromoCode.DiscountType.choices,
            "querystring": querystring,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_coupon_create(request):
    if request.method == "POST":
        form = PromoCodeForm(request.POST)
        if form.is_valid():
            promo = form.save()
            messages.success(request, f"Coupon {promo.code} created.")
            return redirect("dashboard-coupons")
    else:
        form = PromoCodeForm()

    return render(request, "dashboard/coupon_form.html", {"form": form, "mode": "create"})


@login_required
@user_passes_test(_is_staffish)
def dashboard_coupon_edit(request, promo_id: int):
    promo = get_object_or_404(PromoCode.all_objects, id=promo_id)

    if request.method == "POST":
        form = PromoCodeForm(request.POST, instance=promo)
        if form.is_valid():
            promo = form.save()
            messages.success(request, f"Coupon {promo.code} updated.")
            return redirect("dashboard-coupons")
    else:
        form = PromoCodeForm(instance=promo)

    redemptions = PromoRedemption.objects.filter(promo_code=promo).count()
    return render(
        request,
        "dashboard/coupon_form.html",
        {
            "form": form,
            "mode": "edit",
            "promo": promo,
            "redemptions": redemptions,
        },
    )


@login_required
@user_passes_test(_is_staffish)
def dashboard_coupon_delete(request, promo_id: int):
    promo = get_object_or_404(PromoCode.all_objects, id=promo_id)
    if request.method == "POST":
        promo.delete()
        messages.success(request, f"Coupon {promo.code} deleted.")
    return redirect("dashboard-coupons")


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@login_required
@user_passes_test(_is_staffish)
def dashboard_coupon_analytics(request):
    code = (request.GET.get("code") or "").strip().upper()
    start_date = _parse_date(request.GET.get("start_date"))
    end_date = _parse_date(request.GET.get("end_date"))
    if not end_date:
        end_date = timezone.localdate()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max))

    qs = PromoRedemption.objects.filter(created_at__gte=start_dt, created_at__lte=end_dt).select_related("promo_code", "user", "order")
    if code:
        qs = qs.filter(promo_code__code=code)

    totals = qs.aggregate(
        redemptions=Count("id"),
        total_discount=Sum("discount_amount"),
        total_orders=Sum("total_amount"),
        total_shipping=Sum("shipping_amount"),
    )

    top = list(
        qs.values("promo_code__code")
        .annotate(redemptions=Count("id"), total_discount=Sum("discount_amount"))
        .order_by("-redemptions")[:10]
    )

    series = list(
        qs.annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(redemptions=Count("id"), total_discount=Sum("discount_amount"))
        .order_by("day")
    )
    chart_labels = [row["day"].date().isoformat() for row in series]
    chart_values = [int(row["redemptions"] or 0) for row in series]

    recent = list(qs.order_by("-created_at")[:50])

    return render(
        request,
        "dashboard/coupon_analytics.html",
        {
            "code": code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "totals": totals,
            "top_coupons": top,
            "recent_redemptions": recent,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_values_json": json.dumps(chart_values),
        },
    )
