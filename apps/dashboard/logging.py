from __future__ import annotations

from .models import AdminActionLog


def _client_meta(request) -> tuple[str | None, str]:
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return (ip, ua)


def log_admin_action(
    *,
    request,
    action: str,
    entity: str,
    object_ref: str = "",
    message: str = "",
    payload: dict | None = None,
) -> None:
    ip, ua = _client_meta(request)
    actor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    AdminActionLog.objects.create(
        actor=actor,
        action=action,
        entity=entity,
        object_ref=object_ref,
        message=message,
        ip_address=ip,
        user_agent=ua,
        payload=payload or {},
    )

