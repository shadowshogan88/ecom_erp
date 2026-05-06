from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signals  # noqa: F401
        from .signals import ensure_inventory_rows

        post_migrate.connect(ensure_inventory_rows, sender=self)
