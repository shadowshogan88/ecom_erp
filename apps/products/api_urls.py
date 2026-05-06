from rest_framework.routers import DefaultRouter

from .api_views import (
    CategoryViewSet,
    ProductAdminViewSet,
    ProductImageViewSet,
    ProductVariantViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register(r"", ProductViewSet, basename="product")
router.register(r"manage", ProductAdminViewSet, basename="product-manage")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"variants", ProductVariantViewSet, basename="product-variant")
router.register(r"images", ProductImageViewSet, basename="product-image")

urlpatterns = router.urls
