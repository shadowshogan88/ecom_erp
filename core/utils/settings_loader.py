from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.core.cache import cache

CACHE_PREFIX = "db_setting:"
CACHE_TTL_SECONDS = 300


def _cache_key(key: str) -> str:
    return f"{CACHE_PREFIX}{key}"


def _get_setting_model():
    return apps.get_model("settings", "Setting")


def get_setting(key: str, *, default=None) -> str | None:
    cached = cache.get(_cache_key(key))
    if cached is not None:
        return cached

    Setting = _get_setting_model()
    try:
        value = Setting.objects.get(key=key).value
    except Setting.DoesNotExist:
        value = default

    cache.set(_cache_key(key), value, timeout=CACHE_TTL_SECONDS)
    return value


def get_bool_setting(key: str, *, default: bool = False) -> bool:
    raw = get_setting(key, default=None)
    if raw is None:
        return default

    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def get_int_setting(key: str, *, default: int = 0) -> int:
    raw = get_setting(key, default=None)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def get_decimal_setting(key: str, *, default: Decimal = Decimal("0.00")) -> Decimal:
    raw = get_setting(key, default=None)
    if raw is None:
        return default
    try:
        return Decimal(str(raw).strip())
    except (TypeError, ValueError, InvalidOperation):
        return default


def invalidate_setting_cache(key: str) -> None:
    cache.delete(_cache_key(key))
