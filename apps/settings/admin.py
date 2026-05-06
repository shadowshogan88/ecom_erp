from django.contrib import admin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("key", "value", "description")
    ordering = ("key",)
