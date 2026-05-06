from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        # Django 4.2.x + Python 3.14: BaseContext.__copy__ can break when it
        # attempts to copy(super()) (returns a super object). Patch at startup.
        from .django_compat import patch_django_template_basecontext_copy

        patch_django_template_basecontext_copy()

