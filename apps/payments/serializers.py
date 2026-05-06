from __future__ import annotations

from rest_framework import serializers

from apps.orders.models import Order

from .models import Payment, Refund


class PaymentSerializer(serializers.ModelSerializer):
    order_public_id = serializers.CharField(source="order.public_id", read_only=True)
    customer_username = serializers.CharField(source="customer.username", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "public_id",
            "order_public_id",
            "customer_username",
            "method",
            "status",
            "amount",
            "transaction_id",
            "provider_reference",
            "paid_at",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "paid_at", "created_at", "updated_at"]


class PaymentCreateSerializer(serializers.Serializer):
    order_public_id = serializers.CharField()
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    transaction_id = serializers.CharField(required=False, allow_blank=True)
    provider_reference = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_order_public_id(self, value: str):
        order = Order.objects.filter(public_id=value, is_deleted=False).select_related("customer").first()
        if not order:
            raise serializers.ValidationError("Order not found.")

        user = self.context["request"].user
        if not user.is_staff and order.customer_id != user.id:
            raise serializers.ValidationError("Not allowed.")

        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError("Cannot take payment for cancelled order.")

        return value

    def create(self, validated_data):
        request = self.context["request"]
        order = Order.objects.get(public_id=validated_data["order_public_id"])
        payment = Payment.objects.create(
            order=order,
            customer=order.customer,
            method=validated_data["method"],
            amount=validated_data["amount"],
            transaction_id=validated_data.get("transaction_id", ""),
            provider_reference=validated_data.get("provider_reference", ""),
            note=validated_data.get("note", ""),
            created_by=request.user if request.user.is_authenticated else None,
        )
        return payment


class PaymentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Payment.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True)


class RefundSerializer(serializers.ModelSerializer):
    payment_public_id = serializers.CharField(source="payment.public_id", read_only=True)

    class Meta:
        model = Refund
        fields = ["id", "payment_public_id", "status", "amount", "reason", "processed_at", "created_at"]
        read_only_fields = ["id", "processed_at", "created_at"]


class RefundCreateSerializer(serializers.Serializer):
    payment_public_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_payment_public_id(self, value: str):
        payment = Payment.objects.filter(public_id=value, is_deleted=False).select_related("order").first()
        if not payment:
            raise serializers.ValidationError("Payment not found.")
        if payment.status != Payment.Status.PAID:
            raise serializers.ValidationError("Only paid payments can be refunded.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        payment = Payment.objects.get(public_id=validated_data["payment_public_id"])
        refund = Refund.objects.create(
            payment=payment,
            amount=validated_data["amount"],
            reason=validated_data.get("reason", ""),
            created_by=request.user if request.user.is_authenticated else None,
        )
        return refund

