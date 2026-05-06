from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from apps.inventory.models import InventoryItem
from apps.payments.models import Payment
from apps.products.models import Category, Product, ProductImage, ProductVariant
from apps.shipping.models import Courier, DeliveryZone, Shipment


class _BootstrapMixin:
    def _bootstrap(self):
        for name, field in self.fields.items():
            widget = field.widget
            css = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = (css + " form-check-input").strip()
                continue

            if isinstance(widget, forms.Select):
                widget.attrs["class"] = (css + " form-select").strip()
                continue

            widget.attrs["class"] = (css + " form-control").strip()


class ProductForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "category",
            "description",
            "price",
            "discount_type",
            "discount_value",
            "is_active",
            "image",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("sort_order", "name")
        self._bootstrap()


class InventoryAdjustForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["quantity_on_hand", "reorder_level"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class ProductVariantForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["sku", "size", "color", "price_override", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class ProductImageForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "sort_order", "is_primary"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class ShipmentUpdateForm(_BootstrapMixin, forms.Form):
    status = forms.ChoiceField(choices=Shipment.Status.choices)
    tracking_number = forms.CharField(required=False)
    courier = forms.ModelChoiceField(queryset=Courier.objects.filter(is_active=True, is_deleted=False), required=False)
    zone = forms.ModelChoiceField(queryset=DeliveryZone.objects.filter(is_active=True, is_deleted=False), required=False)
    shipping_cost = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class PaymentCreateForm(_BootstrapMixin, forms.Form):
    method = forms.ChoiceField(choices=Payment.Method.choices)
    status = forms.ChoiceField(choices=Payment.Status.choices, initial=Payment.Status.PAID)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    transaction_id = forms.CharField(required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class RefundCreateForm(_BootstrapMixin, forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class AdminProfileForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class SiteContentForm(_BootstrapMixin, forms.Form):
    banner_enabled = forms.BooleanField(required=False, initial=True)
    banner_html = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="HTML allowed (will be rendered as-is).",
    )
    footer_text = forms.CharField(required=False, help_text="Plain text (recommended).")
    free_shipping_enabled = forms.BooleanField(required=False, initial=True)
    free_shipping_threshold = forms.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.00"))
    shipping_fee = forms.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.00"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()
