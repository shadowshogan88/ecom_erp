from __future__ import annotations

from .models import Setting


DEFAULT_SETTINGS = [
    (
        "duplicate_order_enabled",
        "0",
        "If enabled, a customer cannot order the same product again within X days.",
    ),
    (
        "duplicate_order_days",
        "7",
        "Restriction duration (in days) for duplicate order defense.",
    ),
]


def ensure_default_settings(sender, **kwargs):
    for key, value, description in DEFAULT_SETTINGS:
        Setting.objects.get_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )

