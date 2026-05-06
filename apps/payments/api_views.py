from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.orders.models import Order
from apps.dashboard.logging import log_admin_action
from apps.users.permissions import IsStaffUser

from .models import Payment
from .serializers import (
    PaymentCreateSerializer,
    PaymentSerializer,
    PaymentStatusUpdateSerializer,
    RefundCreateSerializer,
    RefundSerializer,
)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Admin/Staff Payment management.
    """

    lookup_field = "public_id"
    lookup_value_regex = r"[^.]+"
    permission_classes = [IsStaffUser]

    def get_queryset(self):
        return Payment.objects.select_related("order", "customer").prefetch_related("refunds").order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentCreateSerializer
        return PaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        log_admin_action(
            request=request._request if hasattr(request, "_request") else request,
            action="create",
            entity="Payment",
            object_ref=payment.public_id,
            message=f"Payment created for order {payment.order.public_id}",
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="status")
    def set_status(self, request, public_id=None):
        payment = self.get_object()
        serializer = PaymentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "").strip()

        update_fields = ["status", "updated_at"]
        old = payment.status
        payment.status = new_status

        if new_status == Payment.Status.PAID and not payment.paid_at:
            payment.paid_at = timezone.now()
            update_fields.append("paid_at")

        if note:
            payment.note = (payment.note or "").strip() + ("\n" if payment.note else "") + note
            update_fields.append("note")

        payment.save(update_fields=update_fields)
        if old != new_status:
            log_admin_action(
                request=request._request if hasattr(request, "_request") else request,
                action="status_change",
                entity="Payment",
                object_ref=payment.public_id,
                message=f"{old} -> {new_status}",
                payload={"note": note},
            )
        return Response(PaymentSerializer(payment).data)

    @action(detail=True, methods=["post"], url_path="refund")
    def create_refund(self, request, public_id=None):
        payment = self.get_object()

        serializer = RefundCreateSerializer(
            data={"payment_public_id": payment.public_id, **request.data},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        log_admin_action(
            request=request._request if hasattr(request, "_request") else request,
            action="create",
            entity="Refund",
            object_ref=str(refund.id),
            message=f"Refund created for payment {payment.public_id}",
        )

        # Mark payment as refunded (simple 1-step refund lifecycle).
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])

        if payment.order and payment.order.payment_status != Order.PaymentStatus.REFUNDED:
            payment.order.payment_status = Order.PaymentStatus.REFUNDED
            payment.order.save(update_fields=["payment_status", "updated_at"])

        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class MyPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Customer view of their payments.
    """

    lookup_field = "public_id"
    lookup_value_regex = r"[^.]+"
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.select_related("order", "customer").filter(customer=self.request.user).order_by("-created_at")
