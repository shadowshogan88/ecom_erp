from django.contrib import admin

from .models import AdminActionLog, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_type", "title", "recipient", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "recipient__username")
    ordering = ("-created_at",)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity", "object_ref", "actor", "ip_address", "created_at")
    list_filter = ("action", "entity", "created_at")
    search_fields = ("entity", "object_ref", "actor__username", "message")
    ordering = ("-created_at",)

# Register your models here.
