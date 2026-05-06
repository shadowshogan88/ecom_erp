from __future__ import annotations

from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    parent_slug = serializers.CharField(source="parent.slug", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "parent_slug", "sort_order", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class ProductImageSerializer(serializers.ModelSerializer):
    product_public_id = serializers.CharField(source="product.public_id", read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "product", "product_public_id", "image", "alt_text", "sort_order", "is_primary", "created_at"]
        read_only_fields = ["id", "created_at", "product_public_id"]


class ProductVariantSerializer(serializers.ModelSerializer):
    product_public_id = serializers.CharField(source="product.public_id", read_only=True)
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "product_public_id",
            "sku",
            "size",
            "color",
            "price_override",
            "final_price",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "product_public_id", "final_price"]


class ProductPublicSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "public_id",
            "name",
            "slug",
            "description",
            "price",
            "final_price",
            "discount_type",
            "discount_value",
            "category_slug",
            "category_name",
            "is_active",
            "image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductAdminSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "public_id",
            "name",
            "slug",
            "description",
            "category",
            "price",
            "discount_type",
            "discount_value",
            "final_price",
            "is_active",
            "image",
            "images",
            "variants",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "final_price", "created_at", "updated_at", "images", "variants"]
