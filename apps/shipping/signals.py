from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Shipment, ShipmentTrackingEvent


@receiver(post_save, sender=Shipment)
def create_initial_shipment_tracking(sender, instance: Shipment, created: bool, **kwargs):
    if not created:
        return
    ShipmentTrackingEvent.objects.create(shipment=instance, status=instance.status, note="Shipment created")

