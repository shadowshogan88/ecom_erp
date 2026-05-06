from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS


def _is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", "") == "admin"))


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or getattr(user, "role", "") in {"admin", "staff"}))


class IsAdminUser(BasePermission):
    message = "Admin access required."

    def has_permission(self, request, view):
        return _is_admin(request.user)


class IsStaffUser(BasePermission):
    message = "Staff access required."

    def has_permission(self, request, view):
        return _is_staff(request.user)


class IsStaffOrReadOnly(BasePermission):
    message = "Staff access required for write operations."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return _is_staff(request.user)

