from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel
from core.utils.settings_loader import invalidate_setting_cache


class Setting(TimeStampedModel):
    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_setting_cache(self.key)

    def delete(self, using=None, keep_parents=False):
        key = self.key
        result = super().delete(using=using, keep_parents=keep_parents)
        invalidate_setting_cache(key)
        return result
