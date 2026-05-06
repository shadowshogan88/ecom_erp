from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Order, OrderTracking


@receiver(pre_save, sender=Order)
def capture_old_order_status(sender, instance: Order, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = (
        Order.all_objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


@receiver(post_save, sender=Order)
def create_order_tracking(sender, instance: Order, created: bool, **kwargs):
    note = getattr(instance, "_tracking_note", "")
    old_status = getattr(instance, "_old_status", None)

    if created:
        OrderTracking.objects.create(order=instance, status=instance.status, note=note or "Order created")
        return

    if old_status and old_status != instance.status:
        OrderTracking.objects.create(order=instance, status=instance.status, note=note or "Status updated")

