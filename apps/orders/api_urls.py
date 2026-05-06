from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import OrderPublicTrackingAPIView, OrderViewSet

router = DefaultRouter()
router.register(r"", OrderViewSet, basename="order")

urlpatterns = [
    path("track/<path:public_id>/", OrderPublicTrackingAPIView.as_view(), name="public-tracking"),
]
urlpatterns += router.urls
