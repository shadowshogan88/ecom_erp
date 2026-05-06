from decimal import Decimal
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Category, Product, ProductVariant, WishlistItem


def _enrich_products_for_ui(products):
    for p in products:
        primary = p.primary_image_obj
        hover = p.hover_image_obj

        p.ui_primary_image = primary.image if primary else p.image
        p.ui_hover_image = hover.image if hover else None

        variants = [v for v in getattr(p, "variants", []).all() if v.is_active and not v.is_deleted]
        colors = []
        for v in variants:
            c = (v.color or "").strip()
            if c and c not in colors:
                colors.append(c)
            if len(colors) >= 3:
                break
        sizes = set((v.size or "").strip() for v in variants if (v.size or "").strip())

        p.ui_colors = colors
        p.ui_sizes_count = len(sizes)


def _wants_json(request) -> bool:
    if (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept


def _referer_path(request, *, default: str = "/") -> str:
    referer = request.headers.get("Referer") or ""
    parsed = urlparse(referer)
    if not parsed.path:
        return default
    return parsed.path + (("?" + parsed.query) if parsed.query else "")


def home(request):
    latest_products = list(
        Product.objects.filter(is_active=True).order_by("-created_at")[:8]
    )
    return render(request, "pages/home.html", {"latest_products": latest_products})


def product_list(request):
    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    quick_filter = (request.GET.get("filter") or "").strip()
    sort = (request.GET.get("sort") or "featured").strip()

    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("images", "variants")
        .order_by("-created_at")
    )
    if q:
        products = products.filter(name__icontains=q)

    if category:
        products = products.filter(category__slug=category)

    if quick_filter == "sale":
        products = products.exclude(discount_type=Product.DiscountType.NONE).filter(discount_value__gt=0)
    elif quick_filter == "new":
        products = products.order_by("-created_at")

    if sort == "price-low":
        final_price = Case(
            When(
                discount_type=Product.DiscountType.PERCENT,
                discount_value__gt=0,
                then=ExpressionWrapper(
                    F("price") - (F("price") * (F("discount_value") / Value(Decimal("100")))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
            When(
                discount_type=Product.DiscountType.FIXED,
                discount_value__gt=0,
                then=ExpressionWrapper(
                    F("price") - F("discount_value"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
            default=F("price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        products = products.annotate(_final_price=final_price).order_by("_final_price", "-created_at")
    elif sort == "price-high":
        final_price = Case(
            When(
                discount_type=Product.DiscountType.PERCENT,
                discount_value__gt=0,
                then=ExpressionWrapper(
                    F("price") - (F("price") * (F("discount_value") / Value(Decimal("100")))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
            When(
                discount_type=Product.DiscountType.FIXED,
                discount_value__gt=0,
                then=ExpressionWrapper(
                    F("price") - F("discount_value"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
            default=F("price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        products = products.annotate(_final_price=final_price).order_by("-_final_price", "-created_at")
    elif sort == "newest":
        products = products.order_by("-created_at")
    elif sort == "rating":
        # Placeholder: no rating field yet.
        products = products.order_by("-created_at")

    categories = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .annotate(
            product_count=Count(
                "products",
                filter=Q(products__is_active=True, products__is_deleted=False),
                distinct=True,
            )
        )
        .order_by("sort_order", "name")
    )

    paginator = Paginator(products, 16)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    _enrich_products_for_ui(page_obj.object_list)

    # Mark wishlisted products for the current user (UI fill state).
    wishlisted_product_ids: set[int] = set()
    if request.user.is_authenticated and page_obj.object_list:
        product_ids = [p.id for p in page_obj.object_list]
        wishlisted_product_ids = set(
            WishlistItem.objects.filter(user=request.user, product_id__in=product_ids).values_list("product_id", flat=True)
        )
    for p in page_obj.object_list:
        p.ui_is_wishlisted = p.id in wishlisted_product_ids

    return render(
        request,
        "pages/product_list.html",
        {
            "page_obj": page_obj,
            "products_count": paginator.count,
            "q": q,
            "categories": categories,
            "active_category": category,
            "active_filter": quick_filter,
            "active_sort": sort,
        },
    )


def product_detail(request, slug):
    """
    Storefront product detail page.

    Shows:
      - Product gallery (Product.image + ProductImage rows)
      - Variant selectors (Color / Size) derived from variants + AttributeValue metadata

    Note: Cart currently adds by product, not variant. We still render selectors for UX and future extension.
    """

    variant_qs = (
        ProductVariant.objects.filter(is_active=True)
        .select_related("inventory_item")
        .prefetch_related(
            "variant_attributes__attribute",
            "variant_attributes__attribute_value",
        )
        .order_by("sku")
    )

    product_qs = (
        Product.objects.filter(is_active=True)
        .prefetch_related("images")
        .prefetch_related(models.Prefetch("variants", queryset=variant_qs))
    )
    product = get_object_or_404(product_qs, slug=slug)

    if request.user.is_authenticated:
        product.ui_is_wishlisted = WishlistItem.objects.filter(user=request.user, product=product).exists()

    # -------------------------
    # Gallery images
    # -------------------------
    gallery_images: list[dict] = []
    seen_urls: set[str] = set()

    def _push_image(url: str, *, alt: str = "", source: str = ""):
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        gallery_images.append({"url": url, "alt": alt, "source": source})

    if product.image:
        _push_image(product.image.url, alt=product.name, source="product.image")

    for img in list(product.images.all().order_by("sort_order", "id")):
        _push_image(img.image.url, alt=(img.alt_text or product.name), source="product.images")

    # -------------------------
    # Variant selectors
    # -------------------------
    variants = list(product.variants.all())

    def _find_attr_value(variant: ProductVariant, *, attr_name: str, attr_type: str | None = None):
        name_key = (attr_name or "").strip().lower()
        for link in variant.variant_attributes.all():
            a = link.attribute
            if not a:
                continue
            if name_key and (a.name or "").strip().lower() == name_key:
                return link.attribute_value
            if attr_type and (a.attribute_type or "").strip().lower() == (attr_type or "").strip().lower():
                return link.attribute_value
        return None

    colors_by_key: dict[str, dict] = {}
    sizes_by_key: dict[str, dict] = {}

    variants_data: list[dict] = []
    availability: dict[str, set[str]] = {}

    for v in variants:
        color_av = _find_attr_value(v, attr_name="color", attr_type="color")
        size_av = _find_attr_value(v, attr_name="size")

        color_value = (getattr(color_av, "value", "") or v.color or "").strip()
        size_value = (getattr(size_av, "value", "") or v.size or "").strip()

        if not color_value and not size_value:
            continue

        color_key = color_value.lower()
        size_key = size_value.lower()

        if color_value:
            colors_by_key.setdefault(
                color_key,
                {
                    "value": color_value,
                    "color_code": (getattr(color_av, "color_code", "") or "").strip(),
                    "image_url": (color_av.image.url if getattr(color_av, "image", None) else ""),
                },
            )

        if size_value:
            sizes_by_key.setdefault(size_key, {"value": size_value})

        if color_value and size_value:
            availability.setdefault(color_key, set()).add(size_value)

        inv = getattr(v, "inventory_item", None)
        variants_data.append(
            {
                "id": v.id,
                "sku": v.sku,
                "color": color_value,
                "size": size_value,
                "is_default": bool(v.is_default),
                "image_url": v.image.url if getattr(v, "image", None) else "",
                "color_code": (getattr(color_av, "color_code", "") or "").strip(),
                "color_image_url": (color_av.image.url if getattr(color_av, "image", None) else ""),
                "price": str(v.final_price),
                "stock": int(getattr(inv, "quantity_on_hand", 0) or 0),
            }
        )

    # Pick defaults from the default variant (fallback to first available).
    default_variant = next((v for v in variants_data if v.get("is_default")), None) or (variants_data[0] if variants_data else None)
    selected_color = (default_variant.get("color") if default_variant else "") or ""
    selected_size = (default_variant.get("size") if default_variant else "") or ""

    # Convert availability sets -> lists for JSON serialization.
    availability_data = {k: sorted(list(v)) for k, v in availability.items()}

    def _size_sort_key(row: dict):
        raw = (row.get("value") or "").strip()
        try:
            return (0, float(raw))
        except Exception:
            return (1, raw.lower())

    context = {
        "product": product,
        "gallery_images": gallery_images,
        "color_options": sorted(list(colors_by_key.values()), key=lambda r: (r.get("value") or "").lower()),
        "size_options": sorted(list(sizes_by_key.values()), key=_size_sort_key),
        "selected_color": selected_color,
        "selected_size": selected_size,
        "variants_data": variants_data,
        "availability_data": availability_data,
    }
    return render(request, "pages/product_detail.html", context)


def categories_view(request):
    """
    Category landing page (Stride template equivalent of /categories/).
    """
    all_categories = list(
        Category.objects.filter(is_active=True, is_deleted=False)
        .only("id", "name", "slug", "parent_id", "description", "image", "sort_order")
        .order_by("sort_order", "name")
    )
    if not all_categories:
        return render(request, "pages/categories.html", {"categories": []})

    category_ids = [c.id for c in all_categories]
    direct_counts = {
        row["category_id"]: row["cnt"]
        for row in (
            Product.objects.filter(is_active=True, is_deleted=False, category_id__in=category_ids)
            .order_by()
            .values("category_id")
            .annotate(cnt=Count("id"))
        )
    }

    children_by_parent: dict[int | None, list[Category]] = {}
    for c in all_categories:
        children_by_parent.setdefault(c.parent_id, []).append(c)

    totals: dict[int, int] = {}

    def rollup(cat: Category) -> int:
        if cat.id in totals:
            return totals[cat.id]
        total = int(direct_counts.get(cat.id, 0))
        for child in children_by_parent.get(cat.id, []):
            total += rollup(child)
        totals[cat.id] = total
        return total

    top_categories = children_by_parent.get(None, [])
    for c in top_categories:
        c.ui_products_count = rollup(c)

    return render(request, "pages/categories.html", {"categories": top_categories})


def wishlist_view(request):
    if not request.user.is_authenticated:
        recommended = list(
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("images", "variants")
            .order_by("-created_at")[:4]
        )
        _enrich_products_for_ui(recommended)
        for p in recommended:
            p.ui_is_wishlisted = False

        return render(
            request,
            "pages/wishlist.html",
            {
                "wishlist_products": [],
                "wishlist_count": 0,
                "recommended_products": recommended,
                "requires_login": True,
            },
        )

    wishlist_rows = list(
        WishlistItem.objects.filter(user=request.user)
        .select_related("product", "product__category")
        .prefetch_related("product__images", "product__variants")
        .order_by("-created_at")
    )
    products = [
        row.product
        for row in wishlist_rows
    ]
    if products:
        _enrich_products_for_ui(products)
        for p in products:
            p.ui_is_wishlisted = True

    recommended_qs = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("images", "variants")
        .order_by("-created_at")
    )
    if wishlist_rows:
        recommended_qs = recommended_qs.exclude(id__in=[row.product_id for row in wishlist_rows])
    recommended = list(recommended_qs[:4])
    if recommended:
        _enrich_products_for_ui(recommended)
        for p in recommended:
            p.ui_is_wishlisted = False

    return render(
        request,
        "pages/wishlist.html",
        {
            "wishlist_products": products,
            "wishlist_count": len(products),
            "recommended_products": recommended,
            "requires_login": False,
        },
    )


@require_POST
def wishlist_toggle_view(request, product_public_id: str):
    if not request.user.is_authenticated:
        login_url = reverse("users:login")
        referer = request.headers.get("Referer") or ""
        parsed = urlparse(referer)
        next_url = (parsed.path or "/") + (("?" + parsed.query) if parsed.query else "")
        if _wants_json(request):
            return JsonResponse(
                {"detail": "Authentication required", "login_url": f"{login_url}?next={next_url}"},
                status=401,
            )
        return redirect(f"{login_url}?next={next_url}")

    product = get_object_or_404(Product.objects.filter(is_active=True), public_id=product_public_id)

    existing = WishlistItem.all_objects.filter(user=request.user, product=product).first()
    if existing and not existing.is_deleted:
        existing.delete()
        wishlisted = False
    elif existing and existing.is_deleted:
        existing.is_deleted = False
        existing.deleted_at = None
        existing.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        wishlisted = True
    else:
        WishlistItem.objects.create(user=request.user, product=product)
        wishlisted = True

    count = WishlistItem.objects.filter(user=request.user).count()

    if _wants_json(request):
        return JsonResponse({"wishlisted": wishlisted, "product_public_id": product.public_id, "count": count})

    return redirect(_referer_path(request, default=reverse("products:wishlist")))


@login_required
@require_POST
def wishlist_clear_view(request):
    WishlistItem.objects.filter(user=request.user).delete()
    if _wants_json(request):
        return JsonResponse({"cleared": True, "count": 0})
    return redirect(_referer_path(request, default=reverse("products:wishlist")))
