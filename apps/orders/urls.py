from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/coupon/apply/", views.apply_coupon_ajax, name="apply-coupon"),
    path("cart/coupon/remove/", views.remove_coupon_ajax, name="remove-coupon"),
    path("cart/add/<path:product_public_id>/", views.add_to_cart_view, name="add-to-cart"),
    path("cart/update/<path:product_public_id>/", views.update_cart_item_view, name="update-cart-item"),
    path("cart/remove/<path:product_public_id>/", views.remove_from_cart_view, name="remove-from-cart"),
    path("cart/clear/", views.clear_cart_view, name="clear-cart"),
    path("checkout/", views.checkout_view, name="checkout"),
    path("orders/", views.order_history_view, name="history"),
    path("orders/<path:public_id>/tracking/", views.order_tracking_view, name="tracking"),
    path("track-order/", views.track_order_lookup_view, name="track-order"),
]
