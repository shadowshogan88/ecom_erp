from __future__ import annotations

from apps.orders.cart import get_cart
from core.utils.settings_loader import get_bool_setting, get_setting


def cart_context(request):
    cart = get_cart(request)
    cart_count = sum(cart.values())

    wishlist_count = 0
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        from apps.products.models import WishlistItem

        wishlist_count = WishlistItem.objects.filter(user=user).count()

    return {"cart_count": cart_count, "wishlist_count": wishlist_count}


def site_content(request):
    banner_enabled = get_bool_setting("site.banner_enabled", default=True)
    banner_html = get_setting(
        "site.banner_html",
        default=(
            '<div class="bg-gradient-to-r from-primary-600 to-primary-500 py-2 text-center text-sm font-medium text-white">'
            "Free shipping on orders over $75 | Use code <span class=\"font-bold\">STRIDE20</span> for 20% off your first order"
            "</div>"
        ),
    )
    footer_text = get_setting("site.footer_text", default="© 2026 SynckBD. All rights reserved.")

    return {
        "site_banner_enabled": banner_enabled,
        "site_banner_html": banner_html or "",
        "site_footer_text": footer_text or "",
    }
