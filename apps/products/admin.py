from django.contrib import admin

from .models import Category, Product, ProductImage, ProductVariant, WishlistItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "sort_order", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")
    readonly_fields = ("created_at", "updated_at")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "public_id", "category", "price", "discount_type", "discount_value", "is_active", "created_at")
    list_filter = ("is_active", "category", "discount_type", "created_at", "updated_at")
    search_fields = ("name", "public_id", "slug", "category__name")
    ordering = ("-created_at",)
    inlines = [ProductImageInline, ProductVariantInline]
    readonly_fields = ("public_id", "sequence_number", "sequence_year", "sequence_month", "created_at", "updated_at")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at", "is_deleted")
    list_filter = ("is_deleted", "created_at")
    search_fields = ("user__username", "user__email", "product__name", "product__public_id")
    autocomplete_fields = ("user", "product")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "deleted_at")
