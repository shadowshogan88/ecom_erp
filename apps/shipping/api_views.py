from __future__ import annotations

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.logging import log_admin_action
from apps.users.permissions import IsStaffUser

from .models import Courier, DeliveryZone, Shipment
from .serializers import (
    CourierSerializer,
    DeliveryZoneSerializer,
    ShipmentCreateSerializer,
    ShipmentSerializer,
    ShipmentStatusUpdateSerializer,
)


class DeliveryZoneViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = DeliveryZoneSerializer
    queryset = DeliveryZone.objects.order_by("name")


class CourierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = CourierSerializer
    queryset = Courier.objects.order_by("name")


class ShipmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = ShipmentSerializer
    queryset = Shipment.objects.select_related("order", "zone", "courier").prefetch_related("tracking_events").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = ShipmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save()
        log_admin_action(
            request=request._request if hasattr(request, "_request") else request,
            action="create",
            entity="Shipment",
            object_ref=str(shipment.id),
            message=f"Shipment created for order {shipment.order.public_id}",
        )
        return Response(ShipmentSerializer(shipment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="status")
    def set_status(self, request, pk=None):
        shipment = self.get_object()
        serializer = ShipmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old = shipment.status
        shipment.set_status(status=serializer.validated_data["status"], note=serializer.validated_data.get("note", ""))
        if old != shipment.status:
            log_admin_action(
                request=request._request if hasattr(request, "_request") else request,
                action="status_change",
                entity="Shipment",
                object_ref=str(shipment.id),
                message=f"{old} -> {shipment.status}",
            )
        return Response(ShipmentSerializer(shipment).data)


class ShipmentPublicTrackingAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, order_public_id: str):
        shipment = (
            Shipment.objects.select_related("order", "zone", "courier")
            .prefetch_related("tracking_events")
            .filter(order__public_id=order_public_id, is_deleted=False)
            .first()
        )
        if not shipment:
            return Response({"detail": "Shipment not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ShipmentSerializer(shipment).data)
