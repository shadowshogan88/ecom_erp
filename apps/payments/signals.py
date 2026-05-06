from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order

from .models import Payment


@receiver(post_save, sender=Payment)
def sync_order_payment_status(sender, instance: Payment, **kwargs):
    order = instance.order
    if not order or order.is_deleted:
        return

    new_status: str | None = None
    if instance.status == Payment.Status.PAID:
        new_status = Order.PaymentStatus.PAID
    elif instance.status == Payment.Status.REFUNDED:
        new_status = Order.PaymentStatus.REFUNDED
    elif instance.status in {Payment.Status.PENDING, Payment.Status.FAILED, Payment.Status.CANCELLED}:
        # Leave as unpaid unless already paid/refunded.
        if order.payment_status not in {Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED}:
            new_status = Order.PaymentStatus.UNPAID

    if new_status and order.payment_status != new_status:
        order.payment_status = new_status
        order.save(update_fields=["payment_status", "updated_at"])

