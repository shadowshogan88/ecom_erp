from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="list"),
    path("categories/", views.categories_view, name="categories"),
    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("wishlist/toggle/<path:product_public_id>/", views.wishlist_toggle_view, name="wishlist-toggle"),
    path("wishlist/clear/", views.wishlist_clear_view, name="wishlist-clear"),
    path("products/<slug:slug>/", views.product_detail, name="detail"),
]
