from __future__ import annotations

from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import InventoryItem
from apps.orders.models import Order

from .models import Notification


@receiver(post_save, sender=Order)
def notify_new_order(sender, instance: Order, created: bool, **kwargs):
    if not created:
        return
    Notification.objects.create(
        recipient=None,
        notification_type=Notification.Type.NEW_ORDER,
        title=f"New order {instance.public_id}",
        message=f"Customer: {instance.customer_id} | Amount: {instance.total_amount}",
        url=reverse("dashboard-order-detail", kwargs={"public_id": instance.public_id}),
    )


@receiver(post_save, sender=InventoryItem)
def notify_low_stock(sender, instance: InventoryItem, **kwargs):
    if instance.reorder_level <= 0:
        return
    if instance.quantity_on_hand > instance.reorder_level:
        return

    since = timezone.now() - timedelta(hours=6)
    exists = Notification.objects.filter(
        notification_type=Notification.Type.LOW_STOCK,
        is_read=False,
        created_at__gte=since,
        message__icontains=f"product_id={instance.product_id}",
    ).exists()
    if exists:
        return

    Notification.objects.create(
        recipient=None,
        notification_type=Notification.Type.LOW_STOCK,
        title=f"Low stock: {instance.product.name}",
        message=f"product_id={instance.product_id} | qty={instance.quantity_on_hand} | reorder={instance.reorder_level}",
        url=f"{reverse('dashboard-inventory')}?low_stock=1",
    )
