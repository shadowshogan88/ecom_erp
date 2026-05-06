from django.apps import AppConfig


class SettingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.settings'

    def ready(self):
        from django.db.models.signals import post_migrate

        from .signals import ensure_default_settings

        post_migrate.connect(ensure_default_settings, sender=self)
