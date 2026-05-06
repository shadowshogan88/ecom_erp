from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import RefreshToken

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def create_access_token(*, user) -> str:
    exp = timezone.now() + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {"type": "access", "user_id": user.id, "exp": int(exp.timestamp())}
    return _encode(payload)


def create_refresh_token(*, user) -> str:
    expires_at = timezone.now() + timedelta(days=REFRESH_TOKEN_DAYS)
    jti = secrets.token_urlsafe(32)
    RefreshToken.objects.create(user=user, jti=jti, expires_at=expires_at)
    payload = {"type": "refresh", "user_id": user.id, "jti": jti, "exp": int(expires_at.timestamp())}
    return _encode(payload)


def rotate_refresh_token(*, refresh_token: str) -> tuple[str, str]:
    """
    Validates refresh token, revokes it, and returns (new_access, new_refresh).
    """
    payload = _decode(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type.")

    user_id = payload.get("user_id")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise ValueError("Invalid token payload.")

    token_obj = RefreshToken.objects.filter(user_id=user_id, jti=jti, revoked_at__isnull=True).first()
    if not token_obj or not token_obj.is_active:
        raise ValueError("Refresh token expired or revoked.")

    token_obj.revoked_at = timezone.now()
    token_obj.save(update_fields=["revoked_at", "updated_at"])

    User = get_user_model()
    user = User.objects.get(pk=user_id)
    return (create_access_token(user=user), create_refresh_token(user=user))


def revoke_refresh_token(*, refresh_token: str) -> None:
    payload = _decode(refresh_token)
    if payload.get("type") != "refresh":
        return
    user_id = payload.get("user_id")
    jti = payload.get("jti")
    if not user_id or not jti:
        return
    RefreshToken.objects.filter(user_id=user_id, jti=jti, revoked_at__isnull=True).update(revoked_at=timezone.now())
