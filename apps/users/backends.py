from __future__ import annotations

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import Q

from .models import User


class EmailOrUsernameBackend(ModelBackend):
    """
    Allows authenticating with either username OR email using the same input field.
    """

    def authenticate(self, request, username=None, password=None, **kwargs) -> AbstractBaseUser | None:
        login_value = (username or kwargs.get(User.USERNAME_FIELD) or "").strip()
        if not login_value or password is None:
            return None

        user = (
            User.objects.filter(Q(username__iexact=login_value) | Q(email__iexact=login_value), is_active=True)
            .order_by("-last_login", "-date_joined", "-id")
            .first()
        )
        if not user:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

