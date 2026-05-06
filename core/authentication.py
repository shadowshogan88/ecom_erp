from __future__ import annotations

from typing import Optional

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


class JWTAuthentication(BaseAuthentication):
    """
    Lightweight JWT auth (HS256) to avoid external dependencies.

    Header: Authorization: Bearer <access_token>
    Payload: {"type": "access", "user_id": <int>, "exp": <unix>}
    """

    keyword = "Bearer"

    def authenticate(self, request):
        raw = get_authorization_header(request)
        if not raw:
            return None

        parts = raw.split()
        if len(parts) == 0:
            return None

        if parts[0].decode().lower() != self.keyword.lower():
            return None

        if len(parts) != 2:
            raise AuthenticationFailed("Invalid Authorization header format.")

        token = parts[1].decode()
        payload = self._decode(token)

        if payload.get("type") != "access":
            raise AuthenticationFailed("Invalid token type.")

        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationFailed("Invalid token payload.")

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found.") from exc

        return (user, None)

    def _decode(self, token: str) -> dict:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("Token expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed("Invalid token.") from exc

