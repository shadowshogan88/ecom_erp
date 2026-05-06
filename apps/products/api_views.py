from __future__ import annotations

from rest_framework import viewsets

from apps.users.permissions import IsStaffOrReadOnly, IsStaffUser

from .models import Category, Product, ProductImage, ProductVariant
from .serializers import (
    CategorySerializer,
    ProductAdminSerializer,
    ProductImageSerializer,
    ProductPublicSerializer,
    ProductVariantSerializer,
)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductPublicSerializer
    lookup_field = "public_id"
    lookup_value_regex = r"[^.]+"

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related("category").order_by("-created_at")


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        return Category.objects.filter(is_deleted=False).select_related("parent").order_by("sort_order", "name")


class ProductAdminViewSet(viewsets.ModelViewSet):
    serializer_class = ProductAdminSerializer
    permission_classes = [IsStaffUser]
    lookup_field = "public_id"
    lookup_value_regex = r"[^.]+"

    def get_queryset(self):
        return Product.all_objects.select_related("category").prefetch_related("images", "variants").order_by("-created_at")


class ProductVariantViewSet(viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    permission_classes = [IsStaffUser]

    def get_queryset(self):
        return ProductVariant.all_objects.select_related("product").order_by("-created_at")


class ProductImageViewSet(viewsets.ModelViewSet):
    serializer_class = ProductImageSerializer
    permission_classes = [IsStaffUser]

    def get_queryset(self):
        return ProductImage.objects.select_related("product").order_by("-created_at")
