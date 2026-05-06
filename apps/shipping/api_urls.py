from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import CourierViewSet, DeliveryZoneViewSet, ShipmentPublicTrackingAPIView, ShipmentViewSet

router = DefaultRouter()
router.register(r"zones", DeliveryZoneViewSet, basename="delivery-zone")
router.register(r"couriers", CourierViewSet, basename="courier")
router.register(r"shipments", ShipmentViewSet, basename="shipment")

urlpatterns = [
    path("track/<path:order_public_id>/", ShipmentPublicTrackingAPIView.as_view(), name="shipment-track"),
]
urlpatterns += router.urls
