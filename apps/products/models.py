from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils.text import slugify

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils.id_generator import next_monthly_id


class Category(SoftDeleteModel, TimeStampedModel):
    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, db_index=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children", db_index=True
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(fields=["parent", "is_active", "sort_order"]),
            models.Index(fields=["is_deleted", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def _ensure_unique_slug(self):
        if self.slug:
            return
        base = slugify(self.name) or "category"
        candidate = base[:110]
        counter = 1
        while Category.all_objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            counter += 1
            suffix = f"-{counter}"
            candidate = f"{base[: (110 - len(suffix))]}{suffix}"
        self.slug = candidate

    def save(self, *args, **kwargs):
        self._ensure_unique_slug()
        return super().save(*args, **kwargs)


class Product(SoftDeleteModel, TimeStampedModel):
    class DiscountType(models.TextChoices):
        NONE = "none", "None"
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    sequence_month = models.PositiveIntegerField(default=0, editable=False, db_index=True)

    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, db_index=True)
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products", db_index=True
    )

    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_type = models.CharField(
        max_length=20, choices=DiscountType.choices, default=DiscountType.NONE, db_index=True
    )
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_deleted", "is_active"]),
            models.Index(fields=["sequence_year", "sequence_month", "sequence_number"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.public_id or 'new'})"

    @property
    def final_price(self):
        from decimal import Decimal

        base = Decimal(self.price or 0)
        value = Decimal(self.discount_value or 0)
        if self.discount_type == Product.DiscountType.PERCENT and value > 0:
            return max(Decimal("0.00"), base - (base * value / Decimal("100")))
        if self.discount_type == Product.DiscountType.FIXED and value > 0:
            return max(Decimal("0.00"), base - value)
        return base

    @property
    def discount_percent(self) -> int:
        """
        Returns a rounded integer discount percentage for UI badges.
        """
        from decimal import Decimal, ROUND_HALF_UP

        base = Decimal(self.price or 0)
        if base <= 0:
            return 0

        value = Decimal(self.discount_value or 0)
        if self.discount_type == Product.DiscountType.PERCENT:
            return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if value > 0 else 0

        if self.discount_type == Product.DiscountType.FIXED and value > 0:
            pct = (value / base) * Decimal("100")
            return int(pct.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        return 0

    def _prefetched_images(self) -> list["ProductImage"]:
        cache = getattr(self, "_prefetched_objects_cache", None) or {}
        if "images" in cache:
            return list(cache["images"])
        return list(self.images.all())

    @property
    def primary_image_obj(self) -> "ProductImage | None":
        images = self._prefetched_images()
        if not images:
            return None
        for img in images:
            if img.is_primary:
                return img
        return images[0]

    @property
    def hover_image_obj(self) -> "ProductImage | None":
        images = self._prefetched_images()
        if len(images) < 2:
            return None
        primary = self.primary_image_obj
        for img in images:
            if primary and img.id == primary.id:
                continue
            return img
        return None

    def _ensure_unique_slug(self):
        if self.slug:
            return

        base = slugify(self.name) or "product"
        candidate = base[:250]
        counter = 1
        while Product.all_objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            counter += 1
            suffix = f"-{counter}"
            candidate = f"{base[: (250 - len(suffix))]}{suffix}"
        self.slug = candidate

    def save(self, *args, **kwargs):
        self._ensure_unique_slug()

        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            monthly = next_monthly_id(Product, prefix="PRD")
            self.public_id = monthly.public_id
            self.sequence_number = monthly.sequence_number
            self.sequence_year = monthly.sequence_year
            self.sequence_month = monthly.sequence_month
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.public_id = ""
                self.sequence_number = 0
                self.sequence_year = 0
                self.sequence_month = 0
                continue
        raise RuntimeError("Failed to generate a unique product public_id after multiple attempts.")


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/images/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_primary = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["product", "is_primary"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} image"


class ProductVariant(SoftDeleteModel, TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    size = models.CharField(max_length=50, blank=True, db_index=True)
    color = models.CharField(max_length=50, blank=True, db_index=True)
    price_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True)
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # Stable signature for "attribute combination" uniqueness per product.
    # Populated by the variant generator; may be NULL for legacy/manual variants.
    signature = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["product", "sku"]
        indexes = [
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["size", "color"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["product", "signature"], name="products_unique_variant_signature"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} - {self.sku}"

    @property
    def final_price(self):
        if self.price_override is not None:
            return self.price_override
        return self.product.final_price


class WishlistItem(SoftDeleteModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        db_index=True,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("user", "product"),)
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["user", "product", "is_deleted"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.product_id}"


class Attribute(SoftDeleteModel, TimeStampedModel):
    """
    Tag-based, dynamic attribute system for product variants.

    Examples:
      - Color (type=color)
      - Size (type=text)
      - Material (type=text)
    """

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        COLOR = "color", "Color"

    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, db_index=True)
    attribute_type = models.CharField(max_length=20, choices=Type.choices, default=Type.TEXT, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(fields=["is_deleted", "is_active", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name

    def _ensure_unique_slug(self):
        if self.slug:
            return
        base = slugify(self.name) or "attribute"
        candidate = base[:110]
        counter = 1
        while Attribute.all_objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            counter += 1
            suffix = f"-{counter}"
            candidate = f"{base[: (110 - len(suffix))]}{suffix}"
        self.slug = candidate

    def save(self, *args, **kwargs):
        self._ensure_unique_slug()
        return super().save(*args, **kwargs)


class AttributeValue(SoftDeleteModel, TimeStampedModel):
    """
    Concrete values for an Attribute.

    For Color:
      - value="Red", color_code="#FF0000", image=<optional>
    """

    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="values", db_index=True)
    value = models.CharField(max_length=100, db_index=True)
    color_code = models.CharField(max_length=20, blank=True, help_text="Optional hex like #FF0000.")
    image = models.ImageField(upload_to="attributes/values/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["attribute", "sort_order", "value"]
        unique_together = (("attribute", "value"),)
        indexes = [
            models.Index(fields=["attribute", "is_active", "sort_order"]),
            models.Index(fields=["attribute", "value"]),
        ]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"


class VariantAttribute(TimeStampedModel):
    """
    Links a ProductVariant to the selected AttributeValue(s).

    We store both `attribute` and `attribute_value` to enforce:
      - one value per attribute per variant (unique constraint on variant+attribute)
    """

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="variant_attributes")
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="variant_links")
    attribute_value = models.ForeignKey(AttributeValue, on_delete=models.PROTECT, related_name="variant_links")

    class Meta:
        ordering = ["variant", "attribute", "id"]
        constraints = [
            models.UniqueConstraint(fields=["variant", "attribute"], name="products_unique_variant_attribute"),
            models.UniqueConstraint(fields=["variant", "attribute_value"], name="products_unique_variant_attribute_value"),
        ]

    def __str__(self) -> str:
        return f"{self.variant_id} {self.attribute_id}={self.attribute_value_id}"

    def clean(self):
        # Keep the redundant attribute FK consistent with the AttributeValue FK.
        if self.attribute_id and self.attribute_value_id and self.attribute_id != self.attribute_value.attribute_id:
            from django.core.exceptions import ValidationError

            raise ValidationError({"attribute_value": "AttributeValue does not belong to the selected Attribute."})

    def save(self, *args, **kwargs):
        # Ensure `attribute` aligns with the value's attribute if not explicitly provided.
        if self.attribute_value_id and not self.attribute_id:
            self.attribute_id = self.attribute_value.attribute_id
        return super().save(*args, **kwargs)
