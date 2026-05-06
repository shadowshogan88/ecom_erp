from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import LoginActivity, RefreshToken, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "public_id", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "public_id", "first_name", "last_name")
    ordering = ("-date_joined",)

    readonly_fields = ("public_id", "sequence_number", "sequence_year")

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Business", {"fields": ("public_id", "role", "sequence_number", "sequence_year")}),
    )


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "jti", "expires_at", "revoked_at", "created_at")
    list_filter = ("expires_at", "revoked_at", "created_at")
    search_fields = ("user__username", "jti")
    ordering = ("-created_at",)


@admin.register(LoginActivity)
class LoginActivityAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "ip_address", "created_at")
    list_filter = ("event", "created_at")
    search_fields = ("user__username", "ip_address", "user_agent")
    ordering = ("-created_at",)
