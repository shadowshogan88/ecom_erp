from __future__ import annotations

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import (
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
    OrderTrackingSerializer,
)


class IsCustomerOrderOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj: Order):
        if request.user and request.user.is_staff:
            return True
        return obj.customer_id == getattr(request.user, "id", None)


class OrderViewSet(viewsets.ModelViewSet):
    lookup_field = "public_id"
    lookup_value_regex = r"[^.]+"

    def get_permissions(self):
        if self.action in {"create", "list", "retrieve", "tracking"}:
            if self.action in {"retrieve", "tracking"}:
                return [permissions.IsAuthenticated(), IsCustomerOrderOwner()]
            return [permissions.IsAuthenticated()]
        if self.action in {"set_status"}:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Order.objects.select_related("customer").prefetch_related("items__product", "tracking")
        if user.is_staff:
            return qs
        return qs.filter(customer=user)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def perform_create(self, serializer):
        return serializer.save()

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        self.check_object_permissions(request, order)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="tracking")
    def tracking(self, request, public_id=None):
        order = self.get_object()
        self.check_object_permissions(request, order)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def set_status(self, request, public_id=None):
        order = self.get_object()

        if not request.user.is_staff and getattr(request.user, "role", "") != "admin":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "")

        if new_status != order.status:
            order.status = new_status
            order._tracking_note = note
            order.save(update_fields=["status", "updated_at"])

        return Response(OrderSerializer(order).data)


class OrderPublicTrackingAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, public_id: str):
        order = Order.objects.prefetch_related("tracking").filter(public_id=public_id).first()
        if not order:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "public_id": order.public_id,
                "status": order.status,
                "tracking": OrderTrackingSerializer(order.tracking.all(), many=True).data,
            }
        )
